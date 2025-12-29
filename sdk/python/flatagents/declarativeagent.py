"""
DeclarativeAgent - A single LLM call configured entirely via YAML or JSON.

See declarative-agent.d.ts for the TypeScript type definition.

An agent is a single LLM call: model + prompts + output schema.
Workflows handle composition, branching, and loops.
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import jinja2
except ImportError:
    jinja2 = None

try:
    import litellm
except ImportError:
    litellm = None


class DeclarativeAgent:
    """
    A single LLM call configured entirely via YAML. No code required.

    v0.4.0 Container format:

        spec: declarative_agent
        spec_version: "0.4.0"

        data:
          name: greeter

          model:
            provider: cerebras
            name: zai-glm-4.6
            temperature: 0.7

          system: "You are a friendly greeter."

          user: |
            Greet the user named {{ input.name }}.

          output:
            greeting:
              type: str
              description: "A friendly greeting message"

        metadata:
          author: "your-name"

    Example usage:
        agent = DeclarativeAgent(config_file="agent.yaml")
        result = await agent.call(name="Alice")
        print(result)  # {"greeting": "Hello, Alice!"}
    """

    SPEC_VERSION = "0.4.0"
    DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

    def __init__(
        self,
        config_file: Optional[str] = None,
        config_dict: Optional[Dict] = None,
        **kwargs
    ):
        if jinja2 is None:
            raise ImportError("jinja2 is required for DeclarativeAgent. Install with: pip install jinja2")
        if litellm is None:
            raise ImportError("litellm is required for DeclarativeAgent. Install with: pip install litellm")

        self._load_config(config_file, config_dict, **kwargs)
        self._validate_spec()
        self._parse_agent_config()

        # Tracking
        self.total_cost = 0.0
        self.total_api_calls = 0

        logger.info(f"Initialized DeclarativeAgent: {self.agent_name}")

    def _load_config(
        self,
        config_file: Optional[str],
        config_dict: Optional[Dict],
        **kwargs
    ):
        """Load v0.4.0 container config."""
        import os
        try:
            import yaml
        except ImportError:
            yaml = None

        config = {}
        if config_file is not None:
            if not os.path.exists(config_file):
                raise FileNotFoundError(f"Configuration file not found: {config_file}")
            with open(config_file, 'r') as f:
                if config_file.endswith('.json'):
                    config = json.load(f) or {}
                else:
                    if yaml is None:
                        raise ImportError("pyyaml is required for YAML config files.")
                    config = yaml.safe_load(f) or {}
        elif config_dict is not None:
            config = config_dict

        self.config = config

        # Extract model config from data section
        data = config.get('data', {})
        model_config = data.get('model', {})

        # Build model name from provider/name
        provider = model_config.get('provider')
        model_name = model_config.get('name')
        if provider and model_name and '/' not in model_name:
            full_model_name = f"{provider}/{model_name}"
        else:
            full_model_name = model_name

        # Set model attributes (with kwargs override)
        self.model = kwargs.get('model', full_model_name)
        self.temperature = kwargs.get('temperature', model_config.get('temperature', 0.7))
        self.max_tokens = kwargs.get('max_tokens', model_config.get('max_tokens', 2048))

    def _validate_spec(self):
        """Validate the spec envelope."""
        config = self.config

        if config.get('spec') != 'declarative_agent':
            raise ValueError(
                f"Invalid spec: expected 'declarative_agent', got '{config.get('spec')}'. "
                "Config must have: spec: declarative_agent"
            )

        if 'data' not in config:
            raise ValueError("Config missing 'data' section")

        spec_version = config.get('spec_version', '')
        if not spec_version.startswith('0.4'):
            logger.warning(f"spec_version '{spec_version}' may not be fully compatible with {self.SPEC_VERSION}")

    def _parse_agent_config(self):
        """Parse the v0.4.0 declarative configuration."""
        data = self.config['data']
        self.metadata = self.config.get('metadata', {})

        # Agent name
        self.agent_name = data.get('name') or self.metadata.get('name', 'unnamed-agent')

        # Prompts
        self._system_prompt = data.get('system', self.DEFAULT_SYSTEM_PROMPT)
        self._user_prompt_template = data.get('user', '')
        self._instruction_suffix = data.get('instruction_suffix', '')

        # Compile Jinja2 template (use default Undefined for optional template variables)
        self._jinja_env = jinja2.Environment()
        self._compiled_user = self._jinja_env.from_string(self._user_prompt_template)

        # Output schema (stored for reference, extraction uses json_object mode)
        self.output_schema = data.get('output', {})

    def _render_user_prompt(self, input_data: Dict[str, Any]) -> str:
        """Render user prompt with input data."""
        prompt = self._compiled_user.render(input=input_data)
        if self._instruction_suffix:
            prompt = f"{prompt}\n\n{self._instruction_suffix}"
        return prompt

    def _build_output_instruction(self) -> str:
        """Build instruction for JSON output based on schema."""
        if not self.output_schema:
            return ""

        fields = []
        for name, field_def in self.output_schema.items():
            desc = field_def.get('description', '')
            field_type = field_def.get('type', 'str')
            enum_vals = field_def.get('enum')

            parts = [f'"{name}"']
            if desc:
                parts.append(f"({desc})")
            if enum_vals:
                parts.append(f"- one of: {enum_vals}")

            fields.append(" ".join(parts))

        return "Respond with JSON containing: " + ", ".join(fields)

    async def call(self, **input_data) -> Dict[str, Any]:
        """
        Execute a single LLM call with the given input.

        Args:
            **input_data: Input values available as {{ input.* }} in templates

        Returns:
            Dict with output fields as defined in the output schema
        """
        user_prompt = self._render_user_prompt(input_data)

        # Add output instruction if we have a schema
        output_instruction = self._build_output_instruction()
        if output_instruction:
            user_prompt = f"{user_prompt}\n\n{output_instruction}"

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        params = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        # Use JSON mode if we have an output schema
        if self.output_schema:
            params["response_format"] = {"type": "json_object"}

        response = await litellm.acompletion(**params)

        # Track usage
        self.total_api_calls += 1
        if hasattr(response, 'usage') and response.usage:
            input_tokens = getattr(response.usage, 'prompt_tokens', 0)
            output_tokens = getattr(response.usage, 'completion_tokens', 0)
            self.total_cost += (input_tokens * 0.001 + output_tokens * 0.002) / 1000

        content = response.choices[0].message.content

        # Parse JSON response if we have an output schema
        if self.output_schema and content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON response: {content}")
                return {"_raw": content}

        return {"_raw": content}

    def call_sync(self, **input_data) -> Dict[str, Any]:
        """Synchronous wrapper for call()."""
        import asyncio
        return asyncio.run(self.call(**input_data))
