"""
Self-contained FlatAgent base class with pluggable LLM backends.

Unifies the agent interface, configuration, and execution loop into a single class.
LLM interaction is delegated to an LLMBackend, allowing different providers.
"""

import asyncio
import os
import random
from abc import ABC, abstractmethod
from typing import Any, Tuple, Callable, List, Dict, Optional, Protocol, runtime_checkable

from .monitoring import get_logger, track_operation

logger = get_logger(__name__)

try:
    import litellm
except ImportError:
    litellm = None

try:
    import aisuite
except ImportError:
    aisuite = None

try:
    import yaml
except ImportError:
    yaml = None

import json


# ─────────────────────────────────────────────────────────────────────────────
# LLM Backend Protocol and Implementations
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMBackend(Protocol):
    """Protocol for LLM backends. Implement this to support different providers."""

    total_cost: float
    total_api_calls: int

    async def call(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """
        Call the LLM with the given messages.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            The LLM response content as a string
        """
        ...

    async def call_raw(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Any:
        """
        Call the LLM and return the raw response object.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            The raw LiteLLM/provider response object
        """
        ...


class LiteLLMBackend:
    """LLM backend using the litellm library."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        retry_delays: Optional[List[float]] = None,
    ):
        if litellm is None:
            raise ImportError("litellm is required. Install with: pip install litellm")

        self.model = model
        self.llm_kwargs = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        }
        self.retry_delays = retry_delays or [1, 2, 4, 8]
        self.total_cost = 0.0
        self.total_api_calls = 0

        logger.info(f"Initialized LiteLLMBackend with model: {model}")

    async def call_raw(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Any:
        """Call the LLM and return the raw response object with retry logic."""
        call_kwargs = {**self.llm_kwargs, **kwargs}

        last_exception = None
        for attempt, delay in enumerate(self.retry_delays):
            try:
                self.total_api_calls += 1
                logger.info(f"Calling LLM (Attempt {attempt + 1}/{len(self.retry_delays)})...")

                response = await litellm.acompletion(
                    model=self.model,
                    messages=messages,
                    **call_kwargs
                )

                if response is None or response.choices is None or len(response.choices) == 0:
                    raise ValueError("Received an empty or invalid response from the LLM.")

                # Track cost if available
                if hasattr(response, '_hidden_params') and 'response_cost' in response._hidden_params:
                    self.total_cost += response._hidden_params['response_cost']

                return response

            except Exception as e:
                last_exception = e
                logger.warning(f"LLM call failed on attempt {attempt + 1}: {e}")
                if attempt < len(self.retry_delays) - 1:
                    jittered_delay = delay + random.random()
                    logger.info(f"Retrying in {jittered_delay:.2f} seconds...")
                    await asyncio.sleep(jittered_delay)

        logger.error("All retry attempts failed.")
        raise last_exception or RuntimeError("LLM call failed after all retries")

    async def call(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Call the LLM and return the content string."""
        response = await self.call_raw(messages, **kwargs)
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("The LLM response content was empty.")
        logger.info(f"LLM response received: '{content[:100]}...'")
        return content


class AISuiteBackend:
    """
    LLM backend using the aisuite library (by Andrew Ng).

    Provides a unified interface to multiple providers:
    OpenAI, Anthropic, Google, AWS, Cohere, Mistral, Ollama, HuggingFace.

    Model format: "provider:model" (e.g., "openai:gpt-4o", "anthropic:claude-3-5-sonnet")
    """

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 1.0,
        retry_delays: Optional[List[float]] = None,
    ):
        if aisuite is None:
            raise ImportError("aisuite is required. Install with: pip install aisuite")

        # Normalize model format: accept both "provider/model" and "provider:model"
        self.model = model.replace("/", ":", 1) if "/" in model else model
        self.llm_kwargs = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
        }
        self.retry_delays = retry_delays or [1, 2, 4, 8]
        self.total_cost = 0.0
        self.total_api_calls = 0
        self.client = aisuite.Client()

        logger.info(f"Initialized AISuiteBackend with model: {self.model}")

    async def call_raw(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Any:
        """Call the LLM and return the raw response object with retry logic."""
        call_kwargs = {**self.llm_kwargs, **kwargs}

        last_exception = None
        for attempt, delay in enumerate(self.retry_delays):
            try:
                self.total_api_calls += 1
                logger.info(f"Calling LLM via AISuite (Attempt {attempt + 1}/{len(self.retry_delays)})...")

                # aisuite is sync-only, wrap in thread for async compatibility
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model,
                    messages=messages,
                    **call_kwargs
                )

                if response is None or response.choices is None or len(response.choices) == 0:
                    raise ValueError("Received an empty or invalid response from the LLM.")

                # Track cost from usage if available
                if hasattr(response, 'usage') and response.usage:
                    # Estimate cost based on token counts (rough estimate)
                    # This is approximate; providers have different pricing
                    usage = response.usage
                    prompt_tokens = getattr(usage, 'prompt_tokens', 0) or 0
                    completion_tokens = getattr(usage, 'completion_tokens', 0) or 0
                    # Very rough estimate: $0.01 per 1K tokens average
                    estimated_cost = (prompt_tokens + completion_tokens) * 0.00001
                    self.total_cost += estimated_cost

                return response

            except Exception as e:
                last_exception = e
                logger.warning(f"AISuite call failed on attempt {attempt + 1}: {e}")
                if attempt < len(self.retry_delays) - 1:
                    jittered_delay = delay + random.random()
                    logger.info(f"Retrying in {jittered_delay:.2f} seconds...")
                    await asyncio.sleep(jittered_delay)

        logger.error("All retry attempts failed.")
        raise last_exception or RuntimeError("AISuite call failed after all retries")

    async def call(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Call the LLM and return the content string."""
        response = await self.call_raw(messages, **kwargs)
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("The LLM response content was empty.")
        logger.info(f"LLM response received: '{content[:100]}...'")
        return content


# ─────────────────────────────────────────────────────────────────────────────
# Extractors (process LiteLLM responses into structured output)
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class Extractor(Protocol):
    """Protocol for response extractors. Process raw LLM responses into structured output."""

    def extract(self, response: Any) -> Any:
        """
        Extract structured data from a raw LLM response.

        Args:
            response: Raw response object from LLMBackend.call_raw()

        Returns:
            Extracted/structured data
        """
        ...


class FreeExtractor:
    """Returns the raw response content as-is. No parsing."""

    def extract(self, response: Any) -> str:
        """Extract raw content string."""
        content = response.choices[0].message.content
        return content if content is not None else ""


class FreeThinkingExtractor:
    """
    Preserves reasoning/thinking from the response.
    Returns: { "thinking": str, "response": str }

    Works with models that return thinking in:
    - A separate 'thinking' field
    - Content blocks with type='thinking'
    - <thinking> tags in content
    """

    def extract(self, response: Any) -> Dict[str, str]:
        """Extract thinking and response separately."""
        import re
        message = response.choices[0].message
        content = message.content or ""
        thinking = ""

        # Check for thinking in message attributes (provider-specific)
        if hasattr(message, 'thinking') and message.thinking:
            thinking = message.thinking
        # Check for thinking in content blocks (Anthropic style)
        elif hasattr(message, 'content_blocks'):
            for block in message.content_blocks or []:
                if getattr(block, 'type', None) == 'thinking':
                    thinking = getattr(block, 'text', '')
                elif getattr(block, 'type', None) == 'text':
                    content = getattr(block, 'text', content)
        # Check for <thinking> tags in content
        elif '<thinking>' in content and '</thinking>' in content:
            match = re.search(r'<thinking>(.*?)</thinking>', content, re.DOTALL)
            if match:
                thinking = match.group(1).strip()
                content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()

        return {"thinking": thinking, "response": content}


class StructuredExtractor:
    """
    Extracts structured JSON output using response_format.
    Requires the LLM call to include response_format parameter.
    """

    def __init__(self, schema: Optional[Dict] = None):
        """
        Args:
            schema: Optional JSON schema for validation
        """
        self.schema = schema

    def extract(self, response: Any) -> Dict[str, Any]:
        """Extract and parse JSON from response."""
        content = response.choices[0].message.content
        if content is None:
            return {}

        try:
            parsed = json.loads(content)
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return {"_raw": content, "_error": str(e)}


class ToolsExtractor:
    """
    Extracts tool calls from the response.
    Returns: { "tool_calls": [...], "content": str }
    """

    def extract(self, response: Any) -> Dict[str, Any]:
        """Extract tool calls and content."""
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = []

        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tc in message.tool_calls:
                tool_call = {
                    "id": getattr(tc, 'id', None),
                    "type": getattr(tc, 'type', 'function'),
                    "function": {
                        "name": tc.function.name if hasattr(tc, 'function') else None,
                        "arguments": tc.function.arguments if hasattr(tc, 'function') else None,
                    }
                }
                # Parse arguments JSON if present
                if tool_call["function"]["arguments"]:
                    try:
                        tool_call["function"]["arguments"] = json.loads(
                            tool_call["function"]["arguments"]
                        )
                    except json.JSONDecodeError:
                        pass  # Keep as string if not valid JSON
                tool_calls.append(tool_call)

        return {"tool_calls": tool_calls, "content": content}


class RegexExtractor:
    """
    Extracts fields from response using regex patterns.
    Patterns are provided at runtime, not in the spec.

    Can extract from:
    - Raw LLM response object (response.choices[0].message.content)
    - Plain string
    """

    def __init__(self, patterns: Dict[str, str], types: Optional[Dict[str, str]] = None):
        """
        Args:
            patterns: Map of field names to regex patterns (must have capture group)
            types: Optional map of field names to type names ('str', 'int', 'float', 'bool', 'json')
        """
        import re
        self.patterns = {name: re.compile(pattern) for name, pattern in patterns.items()}
        self.types = types or {}

    def extract(self, response: Any) -> Optional[Dict[str, Any]]:
        """Extract fields using regex patterns."""
        # Handle both response object and plain string
        if isinstance(response, str):
            content = response
        else:
            content = response.choices[0].message.content

        if content is None:
            return None

        result = {}
        for field_name, pattern in self.patterns.items():
            match = pattern.search(content)
            if not match:
                logger.debug(f"Field '{field_name}' pattern did not match")
                return None

            value = match.group(1)
            field_type = self.types.get(field_name, 'str')

            try:
                if field_type == 'json':
                    result[field_name] = json.loads(value)
                elif field_type == 'int':
                    result[field_name] = int(value)
                elif field_type == 'float':
                    result[field_name] = float(value)
                elif field_type == 'bool':
                    result[field_name] = value.lower() in ('true', '1', 'yes')
                else:
                    result[field_name] = value
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug(f"Failed to parse field '{field_name}': {e}")
                return None

        return result


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool Provider Protocol and Types
# ─────────────────────────────────────────────────────────────────────────────

from dataclasses import dataclass, field


@runtime_checkable
class MCPToolProvider(Protocol):
    """
    Protocol for MCP tool providers.

    Users implement this to connect their MCP backend (e.g., aisuite.mcp.MCPClient).
    The SDK does not provide an implementation - users bring their own.

    Example implementation using aisuite:

        class AISuiteMCPProvider:
            def __init__(self):
                self._clients = {}

            def connect(self, server_name: str, config: dict):
                from aisuite.mcp import MCPClient
                if server_name not in self._clients:
                    self._clients[server_name] = MCPClient.from_config(config)

            def get_tools(self, server_name: str) -> list:
                return self._clients[server_name].list_tools()

            def call_tool(self, server_name: str, tool_name: str, arguments: dict):
                return self._clients[server_name].call_tool(tool_name, arguments)

            def close(self):
                for c in self._clients.values():
                    c.close()
    """

    def connect(self, server_name: str, config: Dict[str, Any]) -> None:
        """
        Connect to an MCP server with the given configuration.

        Args:
            server_name: Identifier for this server (matches key in mcp.servers)
            config: Server configuration (command/args for stdio, server_url for HTTP)
        """
        ...

    def get_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """
        Get available tools from an MCP server.

        Args:
            server_name: Server identifier

        Returns:
            List of tool definitions with 'name', 'description', 'inputSchema'
        """
        ...

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a tool call on an MCP server.

        Args:
            server_name: Server identifier
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        ...

    def close(self) -> None:
        """Cleanup all server connections."""
        ...


@dataclass
class ToolCall:
    """
    Represents a tool call request from the LLM.

    Attributes:
        id: Unique identifier for this tool call (from LLM response)
        server: MCP server name (matches key in mcp.servers config)
        tool: Tool name
        arguments: Tool arguments as a dictionary
    """
    id: str
    server: str
    tool: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """
    Response from an agent call.

    Attributes:
        content: Raw text content from LLM (may be None if only tool calls)
        output: Parsed output according to output schema (if defined)
        tool_calls: List of tool calls requested by LLM (if any)
        raw_response: Raw LLM response object for advanced use cases
    """
    content: Optional[str] = None
    output: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[ToolCall]] = None
    raw_response: Optional[Any] = None


# ─────────────────────────────────────────────────────────────────────────────
# FlatAgent Base Class
# ─────────────────────────────────────────────────────────────────────────────

class FlatAgent(ABC):
    """
    Abstract base class for self-contained flat agents.

    Combines the agent interface, configuration, and execution loop.
    LLM interaction is delegated to a pluggable LLMBackend.

    Configuration can be provided via:
    - config_file: Path to a YAML configuration file
    - config_dict: A dictionary with configuration
    - backend: Custom LLMBackend instance (overrides config-based backend)
    - **kwargs: Override individual parameters

    Example usage:
        class MyAgent(FlatAgent):
            def create_initial_state(self): return {}
            def generate_step_prompt(self, state): return "..."
            def update_state(self, state, result): return {**state, 'result': result}
            def is_solved(self, state): return state.get('done', False)

        # Using config file (creates LiteLLMBackend automatically)
        agent = MyAgent(config_file="config.yaml")

        # Using custom backend
        backend = LiteLLMBackend(model="openai/gpt-4", temperature=0.5)
        agent = MyAgent(backend=backend)

        trace = await agent.execute()
    """

    DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

    def __init__(
        self,
        config_file: Optional[str] = None,
        config_dict: Optional[Dict] = None,
        backend: Optional[LLMBackend] = None,
        **kwargs
    ):
        """
        Initialize the agent with configuration and optional backend.

        Args:
            config_file: Path to YAML config file
            config_dict: Configuration dictionary
            backend: Custom LLMBackend (if not provided, creates LiteLLMBackend from config)
            **kwargs: Override specific config values
        """
        self._load_config(config_file, config_dict, **kwargs)

        if backend is not None:
            self.backend = backend
        else:
            self.backend = self._create_default_backend()

        logger.info(f"Initialized {self.__class__.__name__} with backend: {self.backend.__class__.__name__}")

    def _load_config(
        self,
        config_file: Optional[str],
        config_dict: Optional[Dict],
        **kwargs
    ):
        """Load and process configuration from file (YAML or JSON), dict, or kwargs."""
        config = {}

        if config_file is not None:
            if not os.path.exists(config_file):
                raise FileNotFoundError(f"Configuration file not found: {config_file}")

            with open(config_file, 'r') as f:
                if config_file.endswith('.json'):
                    config = json.load(f) or {}
                else:
                    if yaml is None:
                        raise ImportError("pyyaml is required for YAML config files. Install with: pip install pyyaml")
                    config = yaml.safe_load(f) or {}
        elif config_dict is not None:
            config = config_dict

        model_config = config.get('model', {})
        defaults = config.get('litellm_defaults', {})

        # Build model name from provider/name if needed
        provider = model_config.get('provider')
        model_name = model_config.get('name')
        if provider and model_name and '/' not in model_name:
            full_model_name = f"{provider}/{model_name}"
        else:
            full_model_name = model_name

        def get_value(key: str, fallback: Any) -> Any:
            return kwargs.get(key, model_config.get(key, defaults.get(key, fallback)))

        # Store config values for backend creation
        self.model = kwargs.get('model', full_model_name)
        self.temperature = get_value('temperature', 0.7)
        self.max_tokens = get_value('max_tokens', 2048)
        self.top_p = get_value('top_p', 1.0)
        self.frequency_penalty = get_value('frequency_penalty', 0.0)
        self.presence_penalty = get_value('presence_penalty', 0.0)
        self.retry_delays = model_config.get('retry_delays', [1, 2, 4, 8])

        # Store raw config for subclass access
        self.config = config

    def _create_default_backend(self) -> LLMBackend:
        """Create the default LiteLLMBackend from loaded config."""
        if self.model is None:
            raise ValueError("Model name is required. Provide via config file, config_dict, or 'model' kwarg.")

        return LiteLLMBackend(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            retry_delays=self.retry_delays,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Convenience Properties (delegate to backend)
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def total_cost(self) -> float:
        """Total cost accumulated by the backend."""
        return self.backend.total_cost

    @property
    def total_api_calls(self) -> int:
        """Total API calls made by the backend."""
        return self.backend.total_api_calls

    # ─────────────────────────────────────────────────────────────────────────
    # Abstract Methods (subclasses must implement)
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def create_initial_state(self, *args, **kwargs) -> Any:
        """Create the initial state for the problem."""
        pass

    @abstractmethod
    def generate_step_prompt(self, state: Any) -> str:
        """Generate the user prompt for the next step based on current state."""
        pass

    @abstractmethod
    def update_state(self, current_state: Any, step_result: Any) -> Any:
        """Update the state based on the step result."""
        pass

    @abstractmethod
    def is_solved(self, state: Any) -> bool:
        """Check if the problem is solved."""
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Overridable Hooks
    # ─────────────────────────────────────────────────────────────────────────

    def get_system_prompt(self) -> str:
        """
        Get the system prompt for LLM calls.
        Override to customize the system prompt for your agent.
        """
        return self.DEFAULT_SYSTEM_PROMPT

    def get_response_parser(self) -> Callable[[str], Any]:
        """
        Get the response parser for this agent.
        Override to provide domain-specific parsing of LLM responses.
        """
        return lambda x: x

    def validate_step_result(self, step_result: Any) -> bool:
        """
        Validate that a step result is acceptable before updating state.
        Override for domain-specific validation.
        """
        return step_result is not None

    def step_generator(self, state: Any) -> Tuple[Tuple[str, str], Callable[[str], Any]]:
        """
        Generate the prompt tuple and parser for the current state.

        Returns:
            Tuple of ((system_prompt, user_prompt), response_parser)

        Override for full control over prompt generation.
        """
        system_prompt = self.get_system_prompt()
        user_prompt = self.generate_step_prompt(state)
        parser = self.get_response_parser()
        return (system_prompt, user_prompt), parser

    # ─────────────────────────────────────────────────────────────────────────
    # Execution
    # ─────────────────────────────────────────────────────────────────────────

    async def execute(self, *args, **kwargs) -> List[Any]:
        """
        Execute the agent to solve the problem.

        Args:
            *args, **kwargs: Passed to create_initial_state()

        Returns:
            List of states representing the execution trace
        """
        logger.info(f"Starting execution with args={args}, kwargs={kwargs}")

        state = self.create_initial_state(*args, **kwargs)
        trace = [state]

        while not self.is_solved(state):
            prompt_tuple, parser = self.step_generator(state)
            raw_result = await self._call_llm(prompt_tuple)
            parsed_result = parser(raw_result)

            if not self.validate_step_result(parsed_result):
                logger.warning(f"Step result validation failed: {parsed_result}")

            state = self.update_state(state, parsed_result)
            trace.append(state)
            logger.info("State updated.")

        logger.info(f"Execution completed. Trace length: {len(trace)} states")
        return trace

    async def _call_llm(self, prompt_tuple: Tuple[str, str]) -> str:
        """
        Call the LLM backend with the given prompt.

        Override this for custom pre/post processing around LLM calls.
        """
        system_prompt, user_prompt = prompt_tuple
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self.backend.call(messages)
