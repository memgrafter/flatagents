"""
FlatMachine - State machine orchestration for FlatAgents.

A machine defines how agents are connected and executed:
states, transitions, conditions, and loops.

See local/flatmachines-plan.md for the full specification.
"""

import asyncio
import json
import os
from typing import Any, Dict, Optional

try:
    from jinja2 import Template
except ImportError:
    Template = None

try:
    import yaml
except ImportError:
    yaml = None

from .monitoring import get_logger
from .expressions import get_expression_engine, ExpressionEngine
from .execution import get_execution_type, ExecutionType
from .hooks import MachineHooks, LoggingHooks
from .flatagent import FlatAgent

import uuid
from .persistence import (
    PersistenceBackend,
    LocalFileBackend,
    MemoryBackend,
    CheckpointManager,
    MachineSnapshot
)
from .locking import ExecutionLock, LocalFileLock, NoOpLock
from .actions import (
    Action,
    HookAction,
    MachineInvoker,
    InlineInvoker
)

logger = get_logger(__name__)


class FlatMachine:
    """
    State machine orchestration for FlatAgents.
    
    Executes a sequence of states, evaluations transitions and
    managing context flow between agents.
    
    Supports:
    - Persistence (checkpoint/resume)
    - Concurrency control (locking)
    - Hierarchical execution (machine calls)
    """

    SPEC_VERSION = "0.3.0"

    def __init__(
        self,
        config_file: Optional[str] = None,
        config_dict: Optional[Dict] = None,
        hooks: Optional[MachineHooks] = None,
        persistence: Optional[PersistenceBackend] = None,
        lock: Optional[ExecutionLock] = None,
        invoker: Optional[MachineInvoker] = None,
        **kwargs
    ):
        """
        Initialize the machine.
        
        Args:
            config_file: Path to YAML/JSON config file
            config_dict: Configuration dictionary
            hooks: Custom hooks for extensibility
            persistence: Storage backend (overrides config)
            lock: Concurrency lock (overrides config)
            invoker: Strategy for invoking other machines
            **kwargs: Override config values
        """
        if Template is None:
            raise ImportError("jinja2 is required. Install with: pip install jinja2")

        self.execution_id = str(uuid.uuid4())
        
        # Extract _config_dir override (used for child machines)
        config_dir_override = kwargs.pop('_config_dir', None)
        
        self._load_config(config_file, config_dict)
        
        # Allow parent to override config_dir for child machines
        if config_dir_override:
            self._config_dir = config_dir_override
        
        # Merge kwargs into config data (shallow merge)
        if kwargs and 'data' in self.config:
            self.config['data'].update(kwargs)
            
        self._validate_spec()
        self._parse_machine_config()

        # Set up Jinja2 environment with custom filters
        from jinja2 import Environment
        import json
        self._jinja_env = Environment()
        # Add fromjson filter for parsing JSON strings in templates
        # Usage: {% for item in context.items | fromjson %}
        self._jinja_env.filters['fromjson'] = json.loads

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
        
        # Persistence & Locking
        self._initialize_persistence(persistence, lock)
        
        # Invoker (for child machines)
        self.invoker = invoker or InlineInvoker()

        logger.info(f"Initialized FlatMachine: {self.machine_name} (ID: {self.execution_id})")

    def _initialize_persistence(
        self,
        persistence: Optional[PersistenceBackend],
        lock: Optional[ExecutionLock]
    ) -> None:
        """Initialize persistence and locking components."""
        # Get config
        p_config = self.data.get('persistence', {})
        # Global features config override (simulated for now, would be in kwargs/settings)
        # For now, rely on machine.yml or defaults
        
        enabled = p_config.get('enabled', True) # Default enabled? Or disable? 
        # Plan says: "Global Defaults... backend: local".
        # Let's default to enabled=False for backward compat if not configured? 
        # Or follow plan default? Plan implies explicit configure.
        # Let's default to MemoryBackend if enabled but no backend specified
        
        backend_type = p_config.get('backend', 'memory')
        
        # Persistence Backend
        if persistence:
            self.persistence = persistence
        elif not enabled:
            self.persistence = MemoryBackend() # Fallback, unsaved
        elif backend_type == 'local':
            self.persistence = LocalFileBackend()
        elif backend_type == 'memory':
            self.persistence = MemoryBackend()
        else:
            logger.warning(f"Unknown backend '{backend_type}', using memory")
            self.persistence = MemoryBackend()
            
        # Lock
        if lock:
            self.lock = lock
        elif not enabled:
            self.lock = NoOpLock()
        elif backend_type == 'local':
            self.lock = LocalFileLock() 
        else:
            self.lock = NoOpLock()
            
        # Checkpoint events (default set)
        default_events = ['machine_start', 'state_enter', 'execute', 'state_exit', 'machine_end']
        self.checkpoint_events = set(p_config.get('checkpoint_on', default_events))


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

        # Version check with warning
        self.spec_version = self.config.get('spec_version', '0.1.0')
        major_minor = '.'.join(self.spec_version.split('.')[:2])
        if major_minor not in ['0.1']:
            logger.warning(
                f"Config version {self.spec_version} may not be fully supported. "
                f"Current SDK supports 0.1.x."
            )

        # Schema validation (warnings only, non-blocking)
        try:
            from .validation import validate_flatmachine_config
            validate_flatmachine_config(self.config, warn=True, strict=False)
        except ImportError:
            pass  # jsonschema not installed, skip validation

    def _parse_machine_config(self) -> None:
        """Parse the machine configuration."""
        self.data = self.config['data']
        self.metadata = self.config.get('metadata', {})

        self.machine_name = self.data.get('name', 'unnamed-machine')
        self.initial_context = self.data.get('context', {})
        self.agent_refs = self.data.get('agents', {})
        self.machine_refs = self.data.get('machines', {})
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

    def _get_error_recovery_state(
        self,
        state_config: Dict[str, Any],
        error: Exception
    ) -> Optional[str]:
        """
        Get recovery state from on_error config.
        
        Supports two formats:
        - Simple: on_error: "error_state"
        - Granular: on_error: {default: "error_state", RateLimitError: "retry_state"}
        """
        on_error = state_config.get('on_error')
        if not on_error:
            return None
        
        # Simple format: on_error: "state_name"
        if isinstance(on_error, str):
            return on_error
        
        # Granular format: on_error: {error_type: state_name, default: fallback}
        error_type = type(error).__name__
        return on_error.get(error_type) or on_error.get('default')

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

    def _resolve_config(self, name: str) -> Dict[str, Any]:
        """Resolve a component reference (agent/machine) to a config dict."""
        ref = self.agent_refs.get(name)
        if not ref:
            raise ValueError(f"Unknown component reference: {name}")

        if isinstance(ref, dict):
            return ref

        if isinstance(ref, str):
            path = ref
            if not os.path.isabs(path):
                path = os.path.join(self._config_dir, path)
            
            if not os.path.exists(path):
                raise FileNotFoundError(f"Component file not found: {path}")

            with open(path, 'r') as f:
                if path.endswith('.json'):
                    return json.load(f) or {}
                # Assume yaml
                if yaml:
                    return yaml.safe_load(f) or {}
                raise ImportError("pyyaml required for YAML files")
        
        raise ValueError(f"Invalid reference type: {type(ref)}")

    def _resolve_machine_config(self, name: str) -> Dict[str, Any]:
        """Resolve a machine reference to a config dict."""
        ref = self.machine_refs.get(name)
        if not ref:
            raise ValueError(f"Unknown machine reference: {name}. Check 'machines:' section in config.")

        if isinstance(ref, dict):
            return ref

        if isinstance(ref, str):
            path = ref
            if not os.path.isabs(path):
                path = os.path.join(self._config_dir, path)
            
            if not os.path.exists(path):
                raise FileNotFoundError(f"Machine config file not found: {path}")

            with open(path, 'r') as f:
                if path.endswith('.json'):
                    return json.load(f) or {}
                if yaml:
                    return yaml.safe_load(f) or {}
                raise ImportError("pyyaml required for YAML files")
        
        raise ValueError(f"Invalid machine reference type: {type(ref)}")

    async def _run_hook(self, method_name: str, *args) -> Any:
        """Run a hook method, awaiting if it's a coroutine."""
        method = getattr(self._hooks, method_name)
        result = method(*args)
        if asyncio.iscoroutine(result):
            return await result
        return result

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

        # 1. Handle 'action' (hooks/custom actions)
        action_name = state.get('action')
        if action_name:
            action_impl = HookAction(self._hooks)
            context = await action_impl.execute(action_name, context, config={})

        # 2. Handle 'machine' (child machine execution)
        machine_name = state.get('machine')
        if machine_name:
            target_config = self._resolve_machine_config(machine_name)
            input_spec = state.get('input', {})
            variables = {"context": context, "input": context}
            machine_input = self._render_dict(input_spec, variables)
            output = await self.invoker.invoke(self, target_config, machine_input)
            
            output_mapping = state.get('output_to_context', {})
            if output_mapping:
                safe_output = output or {}
                variables = {"context": context, "output": safe_output, "input": context}
                for ctx_key, template in output_mapping.items():
                    context[ctx_key] = self._render_template(template, variables)

        # 3. Handle 'agent' (LLM execution)
        agent_name = state.get('agent')
        if agent_name:
            agent = self._get_agent(agent_name)
            input_spec = state.get('input', {})
            variables = {"context": context, "input": context}
            agent_input = self._render_dict(input_spec, variables)

            pre_calls = agent.total_api_calls
            pre_cost = agent.total_cost

            execution_config = state.get('execution')
            execution_type = get_execution_type(execution_config)
            output = await execution_type.execute(agent, agent_input)

            self.total_api_calls += agent.total_api_calls - pre_calls
            self.total_cost += agent.total_cost - pre_cost

            if output is None:
                output = {}

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

    async def _save_checkpoint(
        self,
        event: str,
        state_name: str,
        step: int,
        context: Dict[str, Any],
        output: Optional[Dict[str, Any]] = None
    ) -> None:
        """Save a checkpoint if configured."""
        if event not in self.checkpoint_events:
            return

        snapshot = MachineSnapshot(
            execution_id=self.execution_id,
            machine_name=self.machine_name,
            spec_version=self.SPEC_VERSION,
            current_state=state_name,
            context=context,
            step=step,
            event=event,
            output=output
        )
        
        manager = CheckpointManager(self.persistence, self.execution_id)
        await manager.save_checkpoint(snapshot)

    async def execute(
        self,
        input: Optional[Dict[str, Any]] = None,
        max_steps: int = 1000,
        resume_from: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute the machine."""
        if resume_from:
            self.execution_id = resume_from
            logger.info(f"Resuming execution: {self.execution_id}")

        if not await self.lock.acquire(self.execution_id):
            raise RuntimeError(f"Could not acquire lock for execution {self.execution_id}")

        try:
            context = {}
            current_state = None
            step = 0
            final_output = {}
            manager = CheckpointManager(self.persistence, self.execution_id)

            if resume_from:
                snapshot = await manager.load_latest()
                if snapshot:
                    context = snapshot.context
                    step = snapshot.step
                    current_state = snapshot.current_state
                    if snapshot.event == 'machine_end':
                        logger.info("Execution already completed.")
                        return snapshot.output or {}
                    logger.info(f"Restored from snapshot: step={step}, state={current_state}")
                else:
                    logger.warning(f"No snapshot found for {resume_from}, starting fresh.")

            if not current_state:
                current_state = self._initial_state
                input = input or {}
                variables = {"input": input}
                context = self._render_dict(self.initial_context, variables)

                await self._save_checkpoint('machine_start', 'start', step, context)
                context = await self._run_hook('on_machine_start', context)

            logger.info(f"Starting execution loop at: {current_state}")

            while current_state and step < max_steps:
                step += 1
                is_final = current_state in self._final_states

                await self._save_checkpoint('state_enter', current_state, step, context)
                context = await self._run_hook('on_state_enter', current_state, context)

                await self._save_checkpoint('execute', current_state, step, context)

                try:
                    context, output = await self._execute_state(current_state, context)
                    if output and is_final:
                        final_output = output
                except Exception as e:
                    context['last_error'] = str(e)
                    context['last_error_type'] = type(e).__name__
                    
                    state_config = self.states.get(current_state, {})
                    recovery_state = self._get_error_recovery_state(state_config, e)
                    
                    if not recovery_state:
                         recovery_state = await self._run_hook('on_error', current_state, e, context)
                    
                    if recovery_state:
                        logger.warning(f"Error in {current_state}, transitioning to {recovery_state}: {e}")
                        current_state = recovery_state
                        continue
                    raise

                await self._save_checkpoint(
                    'state_exit', 
                    current_state, 
                    step, 
                    context, 
                    output=output if is_final else None
                )

                output = await self._run_hook('on_state_exit', current_state, context, output)

                if is_final:
                    logger.info(f"Reached final state: {current_state}")
                    break

                next_state = self._find_next_state(current_state, context)
                
                if next_state:
                    next_state = await self._run_hook('on_transition', current_state, next_state, context)

                logger.debug(f"Transition: {current_state} -> {next_state}")
                current_state = next_state

            if step >= max_steps:
                logger.warning(f"Machine hit max_steps limit ({max_steps})")

            await self._save_checkpoint('machine_end', 'end', step, context, output=final_output)
            final_output = await self._run_hook('on_machine_end', context, final_output)

            return final_output

        finally:
            await self.lock.release(self.execution_id)

    def execute_sync(
        self,
        input: Optional[Dict[str, Any]] = None,
        max_steps: int = 1000
    ) -> Dict[str, Any]:
        """Synchronous wrapper for execute()."""
        import asyncio
        return asyncio.run(self.execute(input=input, max_steps=max_steps))


__all__ = ["FlatMachine"]
