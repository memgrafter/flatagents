"""
FlatMachine - State machine orchestration for FlatAgents.

A machine defines how agents are connected and executed:
states, transitions, conditions, and loops.

See local/flatmachines-plan.md for the full specification.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

try:
    import jinja2
except ImportError:
    jinja2 = None

try:
    import yaml
except ImportError:
    yaml = None

from .expressions import get_expression_engine, ExpressionEngine
from .execution import get_execution_type, ExecutionType
from .hooks import MachineHooks, LoggingHooks
from .flatagent import FlatAgent


class FlatMachine:
    """
    State machine orchestration for FlatAgents.
    
    Executes a sequence of states, evaluating transitions and
    managing context flow between agents.
    
    Example:
        machine = FlatMachine(config_file="workflow.yml")
        result = await machine.execute(input={"product": "AI tool"})
    """

    SPEC_VERSION = "0.1.0"

    def __init__(
        self,
        config_file: Optional[str] = None,
        config_dict: Optional[Dict] = None,
        hooks: Optional[MachineHooks] = None,
        **kwargs
    ):
        """
        Initialize the machine.
        
        Args:
            config_file: Path to YAML/JSON config file
            config_dict: Configuration dictionary
            hooks: Custom hooks for extensibility
            **kwargs: Override config values
        """
        if jinja2 is None:
            raise ImportError("jinja2 is required. Install with: pip install jinja2")

        self._load_config(config_file, config_dict)
        self._validate_spec()
        self._parse_machine_config()

        # Set up Jinja2 environment
        self._jinja_env = jinja2.Environment()

        # Set up expression engine
        expression_mode = self.data.get("expression_engine", "simple")
        self._expression_engine = get_expression_engine(expression_mode)

        # Hooks
        self._hooks = hooks or MachineHooks()

        # Agent cache
        self._agents: Dict[str, FlatAgent] = {}

        # Execution tracking
        self.total_api_calls = 0
        self.total_cost = 0.0

        logger.info(f"Initialized FlatMachine: {self.machine_name}")

    def _load_config(
        self,
        config_file: Optional[str],
        config_dict: Optional[Dict]
    ) -> None:
        """Load configuration from file or dict."""
        config = {}

        if config_file is not None:
            if not os.path.exists(config_file):
                raise FileNotFoundError(f"Config file not found: {config_file}")

            with open(config_file, 'r') as f:
                if config_file.endswith('.json'):
                    config = json.load(f) or {}
                else:
                    if yaml is None:
                        raise ImportError("pyyaml required for YAML files")
                    config = yaml.safe_load(f) or {}

            # Store config file path for relative agent references
            self._config_dir = os.path.dirname(os.path.abspath(config_file))
        elif config_dict is not None:
            config = config_dict
            self._config_dir = os.getcwd()
        else:
            raise ValueError("Must provide config_file or config_dict")

        self.config = config

    def _validate_spec(self) -> None:
        """Validate the spec envelope."""
        spec = self.config.get('spec')
        if spec != 'flatmachine':
            raise ValueError(
                f"Invalid spec: expected 'flatmachine', got '{spec}'"
            )

        if 'data' not in self.config:
            raise ValueError("Config missing 'data' section")

    def _parse_machine_config(self) -> None:
        """Parse the machine configuration."""
        self.data = self.config['data']
        self.metadata = self.config.get('metadata', {})

        self.machine_name = self.data.get('name', 'unnamed-machine')
        self.initial_context = self.data.get('context', {})
        self.agent_refs = self.data.get('agents', {})
        self.states = self.data.get('states', {})
        self.settings = self.data.get('settings', {})

        # Find initial and final states
        self._initial_state = None
        self._final_states = set()

        for name, state in self.states.items():
            if state.get('type') == 'initial':
                if self._initial_state is not None:
                    raise ValueError("Multiple initial states defined")
                self._initial_state = name
            if state.get('type') == 'final':
                self._final_states.add(name)

        if self._initial_state is None:
            # Default to 'start' if exists, otherwise first state
            if 'start' in self.states:
                self._initial_state = 'start'
            elif self.states:
                self._initial_state = next(iter(self.states))
            else:
                raise ValueError("No states defined")

    def _get_agent(self, agent_name: str) -> FlatAgent:
        """Get or load an agent by name."""
        if agent_name in self._agents:
            return self._agents[agent_name]

        if agent_name not in self.agent_refs:
            raise ValueError(f"Unknown agent: {agent_name}")

        agent_ref = self.agent_refs[agent_name]

        # Handle file path reference
        if isinstance(agent_ref, str):
            if not os.path.isabs(agent_ref):
                agent_ref = os.path.join(self._config_dir, agent_ref)
            agent = FlatAgent(config_file=agent_ref)
        # Handle inline config (dict)
        elif isinstance(agent_ref, dict):
            agent = FlatAgent(config_dict=agent_ref)
        else:
            raise ValueError(f"Invalid agent reference: {agent_ref}")

        self._agents[agent_name] = agent
        return agent

    def _render_template(self, template_str: str, variables: Dict[str, Any]) -> Any:
        """Render a Jinja2 template string."""
        if not isinstance(template_str, str):
            return template_str

        # Check if it's a template
        if '{{' not in template_str:
            return template_str

        template = self._jinja_env.from_string(template_str)
        result = template.render(**variables)

        # Try to parse as JSON for complex types
        try:
            return json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return result

    def _render_dict(self, data: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively render all template strings in a dict."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self._render_template(value, variables)
            elif isinstance(value, dict):
                result[key] = self._render_dict(value, variables)
            elif isinstance(value, list):
                result[key] = [
                    self._render_template(v, variables) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Evaluate a transition condition."""
        variables = {"context": context}
        return bool(self._expression_engine.evaluate(condition, variables))

    def _find_next_state(
        self,
        state_name: str,
        context: Dict[str, Any]
    ) -> Optional[str]:
        """Find the next state based on transitions."""
        state = self.states.get(state_name, {})
        transitions = state.get('transitions', [])

        for transition in transitions:
            condition = transition.get('condition', '')
            to_state = transition.get('to')

            if not to_state:
                continue

            # No condition = default transition
            if not condition:
                return to_state

            # Evaluate condition
            if self._evaluate_condition(condition, context):
                return to_state

        return None

    async def _execute_state(
        self,
        state_name: str,
        context: Dict[str, Any]
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Execute a single state.
        
        Returns:
            Tuple of (updated_context, agent_output)
        """
        state = self.states.get(state_name, {})
        output = None

        # Handle hook actions
        action = state.get('action')
        if action:
            context = self._hooks.on_action(action, context)

        # Handle agent execution
        agent_name = state.get('agent')
        if agent_name:
            agent = self._get_agent(agent_name)

            # Prepare input
            input_spec = state.get('input', {})
            variables = {"context": context, "input": context}
            agent_input = self._render_dict(input_spec, variables)

            # Track pre-call stats to compute delta
            pre_calls = agent.total_api_calls
            pre_cost = agent.total_cost

            # Get execution type from state config
            execution_config = state.get('execution')
            execution_type = get_execution_type(execution_config)

            # Execute agent using the execution type
            output = await execution_type.execute(agent, agent_input)

            # Track costs (delta, not cumulative)
            self.total_api_calls += agent.total_api_calls - pre_calls
            self.total_cost += agent.total_cost - pre_cost

            # Ensure output is a dict
            if output is None:
                output = {}

            # Map output to context
            output_mapping = state.get('output_to_context', {})
            if output_mapping:
                variables = {"context": context, "output": output, "input": context}
                for ctx_key, template in output_mapping.items():
                    context[ctx_key] = self._render_template(template, variables)

        # Handle final state output
        if state.get('type') == 'final':
            output_spec = state.get('output', {})
            if output_spec:
                variables = {"context": context}
                output = self._render_dict(output_spec, variables)

        return context, output

    async def execute(
        self,
        input: Optional[Dict[str, Any]] = None,
        max_steps: int = 1000
    ) -> Dict[str, Any]:
        """
        Execute the machine.
        
        Args:
            input: Initial input values
            max_steps: Maximum number of states to execute (safety limit)
            
        Returns:
            Final output from the machine
        """
        input = input or {}

        # Initialize context from template
        variables = {"input": input}
        context = self._render_dict(self.initial_context, variables)

        # Hook: machine start
        context = self._hooks.on_machine_start(context)

        current_state = self._initial_state
        step = 0
        final_output = {}

        logger.info(f"Starting machine execution at state: {current_state}")

        while current_state and step < max_steps:
            step += 1

            # Check if we're at a final state
            if current_state in self._final_states:
                # Hook: state enter
                context = self._hooks.on_state_enter(current_state, context)

                # Execute final state
                try:
                    context, output = await self._execute_state(current_state, context)
                    if output:
                        final_output = output
                except Exception as e:
                    recovery_state = self._hooks.on_error(current_state, e, context)
                    if recovery_state:
                        current_state = recovery_state
                        continue
                    raise

                # Hook: state exit
                self._hooks.on_state_exit(current_state, context, output)

                logger.info(f"Reached final state: {current_state}")
                break

            # Hook: state enter
            context = self._hooks.on_state_enter(current_state, context)

            # Execute current state
            try:
                context, output = await self._execute_state(current_state, context)
            except Exception as e:
                recovery_state = self._hooks.on_error(current_state, e, context)
                if recovery_state:
                    current_state = recovery_state
                    continue
                raise

            # Hook: state exit
            output = self._hooks.on_state_exit(current_state, context, output)

            # Find next state
            next_state = self._find_next_state(current_state, context)

            if next_state:
                # Hook: transition
                next_state = self._hooks.on_transition(current_state, next_state, context)

            logger.debug(f"Transition: {current_state} -> {next_state}")
            current_state = next_state

        if step >= max_steps:
            logger.warning(f"Machine hit max_steps limit ({max_steps})")

        # Hook: machine end
        final_output = self._hooks.on_machine_end(context, final_output)

        return final_output

    def execute_sync(
        self,
        input: Optional[Dict[str, Any]] = None,
        max_steps: int = 1000
    ) -> Dict[str, Any]:
        """Synchronous wrapper for execute()."""
        import asyncio
        return asyncio.run(self.execute(input=input, max_steps=max_steps))


__all__ = ["FlatMachine"]
