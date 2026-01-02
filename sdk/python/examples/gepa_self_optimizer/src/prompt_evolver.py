"""
Prompt evolution using flatagents.

Implements GEPA's reflective prompt mutation based on execution traces.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from flatagents import setup_logging, get_logger
from .utils import load_agent, update_agent_prompts

# Configure logging
setup_logging(level='INFO')
logger = get_logger(__name__)


@dataclass
class PromptCandidate:
    """A candidate set of improved prompts from reflective update."""
    system_prompt: str
    user_prompt: str
    changes_made: list[str]
    factual_knowledge: list[str]
    strategies_preserved: list[str]


class PromptEvolver:
    """
    Evolves judge prompts using GEPA's reflective update mechanism.

    Uses a flatagent that follows the paper's meta-prompt structure
    for extracting factual knowledge from execution traces.
    """

    def __init__(self, config_dir: Path):
        """Initialize with path to agent configs."""
        self.config_dir = config_dir
        self.agents_dir = config_dir / "agents"

        # Load the reflective updater agent (GEPA's core mutation mechanism)
        self.reflective_updater = load_agent(self.agents_dir / "reflective_updater.yml")

        logger.info("PromptEvolver initialized with reflective updater agent")

    async def reflective_update(
        self,
        current_config: dict,
        traces: list[dict],
    ) -> PromptCandidate:
        """
        GEPA's reflective update: mutate prompt based on execution traces.

        This implements step 4e of Algorithm 1:
        π'_j ← ReflectiveUpdate(π_j, feedbacks, traces)

        Args:
            current_config: Current judge config with system/user prompts
            traces: List of {input, output, feedback} from minibatch execution

        Returns:
            PromptCandidate with mutated prompts
        """
        data = current_config.get("data", {})
        current_system = data.get("system", "")
        current_user = data.get("user", "")

        # Format current instruction as the paper expects
        current_instruction = f"SYSTEM PROMPT:\n{current_system}\n\nUSER PROMPT TEMPLATE:\n{current_user}"

        # Call reflective updater with traces
        result = await self.reflective_updater.call(
            current_instruction=current_instruction,
            traces=traces,
        )

        # Parse new instruction back into system/user prompts
        result_output = result.output or {}
        new_instruction = result_output.get("new_instruction", "")
        system_prompt, user_prompt = self._parse_instruction(
            new_instruction, current_system, current_user
        )

        return PromptCandidate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            changes_made=result_output.get("corrections_made", []),
            factual_knowledge=result_output.get("factual_knowledge_extracted", []),
            strategies_preserved=result_output.get("strategies_preserved", []),
        )

    def _parse_instruction(
        self,
        new_instruction: str,
        fallback_system: str,
        fallback_user: str,
    ) -> tuple[str, str]:
        """
        Parse the new instruction into system and user prompts.

        The reflective updater returns a combined instruction that we need
        to split back into system and user components.
        """
        # Try to find explicit markers
        system_match = re.search(
            r"SYSTEM PROMPT:\s*(.*?)(?=USER PROMPT|USER TEMPLATE|$)",
            new_instruction,
            re.DOTALL | re.IGNORECASE
        )
        user_match = re.search(
            r"USER (?:PROMPT|TEMPLATE)[:\s]*(.*?)$",
            new_instruction,
            re.DOTALL | re.IGNORECASE
        )

        if system_match and user_match:
            system_prompt = system_match.group(1).strip()
            user_prompt = user_match.group(1).strip()
        else:
            # If no clear markers, try to split intelligently
            # Look for common patterns
            if "'''SYSTEM" in new_instruction.upper() or "```SYSTEM" in new_instruction.upper():
                # Extract from code blocks
                blocks = re.findall(r"['\"`]{3}(.*?)['\"`]{3}", new_instruction, re.DOTALL)
                if len(blocks) >= 2:
                    system_prompt = blocks[0].strip()
                    user_prompt = blocks[1].strip()
                elif len(blocks) == 1:
                    # Single block - use as system, keep user
                    system_prompt = blocks[0].strip()
                    user_prompt = fallback_user
                else:
                    system_prompt = fallback_system
                    user_prompt = fallback_user
            elif len(new_instruction) > 100:
                # Use the new instruction as system prompt, keep user template
                system_prompt = new_instruction.strip()
                user_prompt = fallback_user
            else:
                # Fall back to originals
                system_prompt = fallback_system
                user_prompt = fallback_user

        # Clean up any remaining markers
        system_prompt = re.sub(r"^(SYSTEM PROMPT:?\s*)", "", system_prompt, flags=re.IGNORECASE).strip()
        user_prompt = re.sub(r"^(USER (?:PROMPT|TEMPLATE):?\s*)", "", user_prompt, flags=re.IGNORECASE).strip()

        # Ensure we have valid prompts
        if not system_prompt or len(system_prompt) < 20:
            system_prompt = fallback_system
        if not user_prompt or len(user_prompt) < 10:
            user_prompt = fallback_user

        return system_prompt, user_prompt

    def create_candidate_config(
        self,
        original_config: dict,
        candidate: PromptCandidate,
    ) -> dict:
        """Create a new judge config with candidate prompts."""
        return update_agent_prompts(
            original_config,
            candidate.system_prompt,
            candidate.user_prompt,
        )

    def get_stats(self) -> dict:
        """Get statistics about LLM calls made."""
        return {
            "reflective_updater_calls": self.reflective_updater.total_api_calls,
            "reflective_updater_cost": self.reflective_updater.total_cost,
        }
