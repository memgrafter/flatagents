"""
MDAP Orchestration for FlatAgent v0.6.0.

Implements the first-to-ahead-by-k voting mechanism from the MAKER paper.
Handles multi-sampling, regex parsing, validation, and state management.
"""

import copy
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import jsonschema
import litellm

from flatagents import FlatAgent, setup_logging, get_logger

# Configure logging
setup_logging(level='INFO')
logger = get_logger(__name__)


@dataclass
class MDAPConfig:
    """MDAP-specific configuration."""
    k_margin: int = 3
    max_candidates: int = 10
    max_steps: int = 100
    max_response_tokens: int = 2048


@dataclass
class MDAPMetrics:
    """Execution metrics collected during MDAP runs."""
    total_samples: int = 0
    total_red_flags: int = 0
    red_flags_by_reason: Dict[str, int] = field(default_factory=dict)
    samples_per_step: List[int] = field(default_factory=list)

    def record_red_flag(self, reason: str):
        self.total_red_flags += 1
        self.red_flags_by_reason[reason] = self.red_flags_by_reason.get(reason, 0) + 1


class MDAPOrchestrator:
    """
    MDAP voting orchestrator for FlatAgent v0.6.0.

    Uses the agent for prompt rendering, handles LLM calls, regex parsing,
    validation, and voting. State management is external to the agent.
    """

    def __init__(
        self,
        agent: FlatAgent,
        config: Optional[MDAPConfig] = None
    ):
        self.agent = agent
        self.config = config or self._load_config_from_agent()
        self.metrics = MDAPMetrics()

        # Load parsing and validation from metadata
        self._parsing_config = agent.metadata.get('parsing', {})
        self._validation_schema = agent.metadata.get('validation', None)

        # Compile regex patterns
        self._patterns = {}
        for field_name, field_config in self._parsing_config.items():
            pattern = field_config.get('pattern')
            if pattern:
                self._patterns[field_name] = (
                    re.compile(pattern, re.DOTALL),
                    field_config.get('type', 'str')
                )

    def _load_config_from_agent(self) -> MDAPConfig:
        """Load MDAP config from agent's metadata."""
        mdap_config = self.agent.metadata.get('mdap', {})
        return MDAPConfig(
            k_margin=mdap_config.get('k_margin', 3),
            max_candidates=mdap_config.get('max_candidates', 10),
            max_steps=mdap_config.get('max_steps', 100),
            max_response_tokens=mdap_config.get('max_response_tokens', 2048),
        )

    def _parse_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response using regex patterns from config."""
        if not self._patterns:
            return None

        result = {}
        for field_name, (pattern, field_type) in self._patterns.items():
            match = pattern.search(content)
            if match:
                value = match.group(1)
                if field_type == 'json':
                    try:
                        result[field_name] = json.loads(value)
                    except json.JSONDecodeError:
                        return None
                elif field_type == 'int':
                    try:
                        result[field_name] = int(value)
                    except ValueError:
                        return None
                else:
                    result[field_name] = value
            else:
                return None  # Required field missing

        return result

    def _validate_parsed(self, parsed: Dict[str, Any]) -> bool:
        """Validate parsed result against JSON Schema from config."""
        if not self._validation_schema:
            return True

        try:
            jsonschema.validate(instance=parsed, schema=self._validation_schema)
            return True
        except jsonschema.ValidationError:
            return False

    async def sample_once(self, input_data: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Make one LLM call and parse the response.

        Args:
            input_data: Input for the agent (available as {{ input.* }})

        Returns:
            Tuple of (raw_content, parsed_result or None)
        """
        # Render prompts using agent's templates
        system_prompt = self.agent._render_system_prompt(input_data)
        user_prompt = self.agent._render_user_prompt(input_data)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Make LLM call
        response = await litellm.acompletion(
            model=self.agent.model,
            messages=messages,
            temperature=self.agent.temperature,
            max_tokens=self.agent.max_tokens,
        )

        # Track usage
        self.agent.total_api_calls += 1
        if hasattr(response, 'usage') and response.usage:
            input_tokens = getattr(response.usage, 'prompt_tokens', 0)
            output_tokens = getattr(response.usage, 'completion_tokens', 0)
            self.agent.total_cost += (input_tokens * 0.001 + output_tokens * 0.002) / 1000

        content = response.choices[0].message.content

        # Handle null content
        if content is None:
            return "", None

        # Parse response
        parsed = self._parse_response(content)

        return content, parsed

    def _check_red_flags(self, content: str, parsed: Optional[Dict[str, Any]]) -> Optional[str]:
        """Check response for red flags per MAKER paper."""
        # Format flag: parsing failed
        if parsed is None:
            return "format_error"

        # Validation flag
        if not self._validate_parsed(parsed):
            return "validation_failed"

        # Length flag: response too long
        estimated_tokens = len(content) // 4
        if estimated_tokens > self.config.max_response_tokens:
            return "length_exceeded"

        return None

    async def first_to_ahead_by_k(
        self,
        input_data: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """
        Core voting logic - sample until one response leads by k_margin.

        Returns:
            Tuple of (winning_response, num_samples)
        """
        votes: Counter = Counter()
        responses: Dict[str, Dict[str, Any]] = {}
        num_samples = 0

        for _ in range(self.config.max_candidates):
            try:
                content, parsed = await self.sample_once(input_data)
                num_samples += 1
                self.metrics.total_samples += 1

                # Red-flag check
                flag_reason = self._check_red_flags(content, parsed)
                if flag_reason:
                    self.metrics.record_red_flag(flag_reason)
                    logger.debug(f"Red-flagged: {flag_reason}")
                    continue

                logger.debug(f"Parsed result: {parsed}")

                # Vote on parsed result
                key = json.dumps(parsed, sort_keys=True)
                votes[key] += 1
                responses[key] = parsed

                # Check if single response hits k_margin
                if votes[key] >= self.config.k_margin:
                    logger.debug(f"Winner found with {votes[key]} votes after {num_samples} samples")
                    return parsed, num_samples

                # Check if leader ahead by k_margin
                if len(votes) >= 2:
                    top = votes.most_common(2)
                    if top[0][1] - top[1][1] >= self.config.k_margin:
                        logger.debug(f"Leader ahead by k after {num_samples} samples")
                        return responses[top[0][0]], num_samples

            except Exception as e:
                logger.warning(f"Sample failed: {e}")
                continue

        # Majority fallback
        if votes:
            winner_key = votes.most_common(1)[0][0]
            logger.debug(f"Majority fallback after {num_samples} samples")
            return responses[winner_key], num_samples

        logger.warning("No valid responses obtained")
        return None, num_samples

    @property
    def total_api_calls(self) -> int:
        return self.agent.total_api_calls

    @property
    def total_cost(self) -> float:
        return self.agent.total_cost


def create_orchestrator_from_config(config_path: str) -> MDAPOrchestrator:
    """Create orchestrator from YAML config file."""
    agent = FlatAgent(config_file=config_path)
    return MDAPOrchestrator(agent)
