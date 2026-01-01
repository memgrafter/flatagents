"""
Execution Types for FlatMachine.

Execution types customize HOW an agent is called, declared in YAML.
They are orchestration behavior (not agents) - no LLM call of their own.

Built-in types:
- default: Standard single agent call
- mdap_voting: Multi-sample with first-to-ahead-by-k voting
- parallel: Run N samples in parallel, return all
- retry: Retry on failure with backoff

Example YAML:
    states:
      solve_step:
        agent: solver
        execution:
          type: mdap_voting
          k_margin: 3
          max_candidates: 10
"""

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .flatagent import FlatAgent

logger = logging.getLogger(__name__)


# Registry of execution types
_EXECUTION_TYPES: Dict[str, type] = {}


def register_execution_type(name: str):
    """Decorator to register an execution type."""
    def decorator(cls):
        _EXECUTION_TYPES[name] = cls
        return cls
    return decorator


def get_execution_type(config: Optional[Dict[str, Any]] = None) -> "ExecutionType":
    """Get an execution type instance from config."""
    if config is None:
        return DefaultExecution()
    
    type_name = config.get("type", "default")
    if type_name not in _EXECUTION_TYPES:
        raise ValueError(f"Unknown execution type: {type_name}")
    
    cls = _EXECUTION_TYPES[type_name]
    return cls.from_config(config)


class ExecutionType(ABC):
    """Base class for execution types."""
    
    @classmethod
    @abstractmethod
    def from_config(cls, config: Dict[str, Any]) -> "ExecutionType":
        """Create instance from YAML config."""
        pass
    
    @abstractmethod
    async def execute(
        self,
        agent: "FlatAgent",
        input_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the agent with this execution type.
        
        Args:
            agent: The FlatAgent to call
            input_data: Input data for the agent
            
        Returns:
            Agent output dict, or None on failure
        """
        pass


@register_execution_type("default")
class DefaultExecution(ExecutionType):
    """Standard single agent call."""
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "DefaultExecution":
        return cls()
    
    async def execute(
        self,
        agent: "FlatAgent",
        input_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Single agent call."""
        result = await agent.call(**input_data)
        
        if result.output:
            return result.output
        elif result.content:
            return {"content": result.content}
        else:
            return {}


# Parallel Execution Type

@register_execution_type("parallel")
class ParallelExecution(ExecutionType):
    """
    Run N samples in parallel, return all results.
    
    Useful for getting multiple diverse responses to compare or aggregate.
    
    Example YAML:
        execution:
          type: parallel
          n_samples: 5
    """
    
    def __init__(self, n_samples: int = 3):
        self.n_samples = n_samples
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "ParallelExecution":
        return cls(
            n_samples=config.get("n_samples", 3)
        )
    
    async def execute(
        self,
        agent: "FlatAgent",
        input_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Run N agent calls in parallel, return all results."""
        async def single_call():
            result = await agent.call(**input_data)
            if result.output:
                return result.output
            elif result.content:
                return {"content": result.content}
            else:
                return {}
        
        # Run all samples in parallel
        tasks = [single_call() for _ in range(self.n_samples)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = [r for r in results if not isinstance(r, Exception)]
        
        if not valid_results:
            return None
        
        return {
            "results": valid_results,
            "count": len(valid_results)
        }


# Retry Execution Type

@register_execution_type("retry")
class RetryExecution(ExecutionType):
    """
    Retry on failure with exponential backoff.
    
    Useful for handling transient failures (rate limits, network issues).
    
    Example YAML:
        execution:
          type: retry
          max_retries: 3
          backoff: 1.0  # Initial backoff in seconds
          backoff_multiplier: 2.0  # Multiply backoff after each retry
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        backoff: float = 1.0,
        backoff_multiplier: float = 2.0
    ):
        self.max_retries = max_retries
        self.backoff = backoff
        self.backoff_multiplier = backoff_multiplier
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "RetryExecution":
        return cls(
            max_retries=config.get("max_retries", 3),
            backoff=config.get("backoff", 1.0),
            backoff_multiplier=config.get("backoff_multiplier", 2.0)
        )
    
    async def execute(
        self,
        agent: "FlatAgent",
        input_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Execute with retries on failure."""
        last_error = None
        current_backoff = self.backoff
        
        for attempt in range(self.max_retries + 1):
            try:
                result = await agent.call(**input_data)
                
                if result.output:
                    return result.output
                elif result.content:
                    return {"content": result.content}
                else:
                    return {}
                    
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries + 1} failed: {e}"
                )
                
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {current_backoff}s...")
                    await asyncio.sleep(current_backoff)
                    current_backoff *= self.backoff_multiplier
        
        # All retries exhausted
        logger.error(f"All {self.max_retries + 1} attempts failed. Last error: {last_error}")
        return None


# MDAP Voting Execution Type

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


@register_execution_type("mdap_voting")
class MDAPVotingExecution(ExecutionType):
    """
    Multi-sample with first-to-ahead-by-k voting.
    
    Implements the voting algorithm from the MAKER paper.
    """
    
    def __init__(
        self,
        k_margin: int = 3,
        max_candidates: int = 10,
        max_response_tokens: int = 2048
    ):
        self.k_margin = k_margin
        self.max_candidates = max_candidates
        self.max_response_tokens = max_response_tokens
        self.metrics = MDAPMetrics()
        
        # Loaded from agent metadata
        self._patterns: Dict[str, Tuple[re.Pattern, str]] = {}
        self._validation_schema: Optional[Dict] = None
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "MDAPVotingExecution":
        return cls(
            k_margin=config.get("k_margin", 3),
            max_candidates=config.get("max_candidates", 10),
            max_response_tokens=config.get("max_response_tokens", 2048)
        )
    
    def _configure_from_agent(self, agent: "FlatAgent"):
        """Load parsing and validation config from agent metadata."""
        # Check if agent metadata overrides execution config
        mdap_config = agent.metadata.get('mdap', {})
        if mdap_config.get('k_margin'):
            self.k_margin = mdap_config['k_margin']
        if mdap_config.get('max_candidates'):
            self.max_candidates = mdap_config['max_candidates']
        if mdap_config.get('max_response_tokens'):
            self.max_response_tokens = mdap_config['max_response_tokens']

        # Load parsing patterns
        parsing_config = agent.metadata.get('parsing', {})
        self._patterns = {}
        for field_name, field_config in parsing_config.items():
            pattern = field_config.get('pattern')
            if pattern:
                self._patterns[field_name] = (
                    re.compile(pattern, re.DOTALL),
                    field_config.get('type', 'str')
                )

        # Load validation schema
        self._validation_schema = agent.metadata.get('validation', None)
    
    def _parse_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response using regex patterns."""
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
                return None

        return result
    
    def _validate_parsed(self, parsed: Dict[str, Any]) -> bool:
        """Validate parsed result against JSON Schema."""
        if not self._validation_schema:
            return True

        try:
            import jsonschema
            jsonschema.validate(instance=parsed, schema=self._validation_schema)
            return True
        except Exception:
            return False
    
    def _check_red_flags(self, content: str, parsed: Optional[Dict[str, Any]]) -> Optional[str]:
        """Check response for red flags per MAKER paper."""
        if parsed is None:
            return "format_error"

        if not self._validate_parsed(parsed):
            return "validation_failed"

        estimated_tokens = len(content) // 4
        if estimated_tokens > self.max_response_tokens:
            return "length_exceeded"

        return None
    
    async def execute(
        self,
        agent: "FlatAgent",
        input_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Multi-sample with voting - replaces single agent call.
        
        Returns the winning parsed response or None.
        """
        import litellm
        
        self._configure_from_agent(agent)

        votes: Counter = Counter()
        responses: Dict[str, Dict[str, Any]] = {}
        num_samples = 0

        for _ in range(self.max_candidates):
            try:
                # Render prompts
                system_prompt = agent._render_system_prompt(input_data)
                user_prompt = agent._render_user_prompt(input_data)

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]

                response = await litellm.acompletion(
                    model=agent.model,
                    messages=messages,
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens,
                )

                agent.total_api_calls += 1
                num_samples += 1
                self.metrics.total_samples += 1

                content = response.choices[0].message.content
                if content is None:
                    continue

                # Parse and check
                parsed = self._parse_response(content)
                flag_reason = self._check_red_flags(content, parsed)
                
                if flag_reason:
                    self.metrics.record_red_flag(flag_reason)
                    continue

                # Vote
                key = json.dumps(parsed, sort_keys=True)
                votes[key] += 1
                responses[key] = parsed

                # Check for winner
                if votes[key] >= self.k_margin:
                    self.metrics.samples_per_step.append(num_samples)
                    return parsed

                if len(votes) >= 2:
                    top = votes.most_common(2)
                    if top[0][1] - top[1][1] >= self.k_margin:
                        self.metrics.samples_per_step.append(num_samples)
                        return responses[top[0][0]]

            except Exception as e:
                logger.warning(f"Sample failed: {e}")
                continue

        # Majority fallback
        self.metrics.samples_per_step.append(num_samples)
        if votes:
            winner_key = votes.most_common(1)[0][0]
            return responses[winner_key]

        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get collected metrics."""
        return {
            "total_samples": self.metrics.total_samples,
            "total_red_flags": self.metrics.total_red_flags,
            "red_flags_by_reason": self.metrics.red_flags_by_reason,
            "samples_per_step": self.metrics.samples_per_step,
        }


__all__ = [
    "ExecutionType",
    "DefaultExecution",
    "ParallelExecution",
    "RetryExecution",
    "MDAPVotingExecution",
    "get_execution_type",
    "register_execution_type",
]

