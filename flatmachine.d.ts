/**
 * FlatMachine Configuration Schema v0.1.0
 * =============================================
 *
 * A machine defines how agents are connected and executed:
 * states, transitions, conditions, and loops.
 *
 * While flatagents defines WHAT each agent is (model + prompts + output schema),
 * flatmachines defines HOW agents are connected and executed.
 *
 * STRUCTURE:
 * ----------
 * spec           - Fixed string "flatmachine"
 * spec_version   - Semver string (e.g., "0.1.0")
 * data           - The machine configuration
 * metadata       - Extensibility layer
 *
 * DATA FIELDS:
 * ------------
 * name               - Machine identifier
 * expression_engine  - "simple" (default) or "cel"
 * context            - Initial context values (Jinja2 templates)
 * agents             - Map of agent name to config file path or inline config
 * states             - Map of state name to state definition
 * settings           - Optional settings (hooks, etc.)
 *
 * STATE FIELDS:
 * -------------
 * type              - "initial" or "final" (optional)
 * agent             - Agent name to execute (from agents map)
 * execution         - Execution type config: {type: "retry", backoffs: [...], jitter: 0.1}
 * on_error          - Error handling: "error_state" or {default: "...", ErrorType: "..."}
 * action            - Hook action to execute
 * input             - Input mapping (Jinja2 templates)
 * output_to_context - Map agent output to context (Jinja2 templates)
 * output            - Final output (for final states)
 * transitions       - Ordered list of transitions
 *
 * TRANSITION FIELDS:
 * ------------------
 * condition         - Expression to evaluate (optional, default: always true)
 * to                - Target state name
 *
 * EXPRESSION SYNTAX (Simple Mode):
 * --------------------------------
 * Comparisons: ==, !=, <, <=, >, >=
 * Boolean: and, or, not
 * Field access: context.field, input.field, output.field
 * Literals: "string", 42, true, false, null
 *
 * Example: "context.score >= 8 and context.round < 4"
 *
 * EXPRESSION SYNTAX (CEL Mode):
 * -----------------------------
 * All simple syntax, plus:
 * List macros: context.items.all(i, i > 0)
 * String methods: context.name.startsWith("test")
 * Timestamps: context.created > now - duration("24h")
 *
 * EXAMPLE CONFIGURATION:
 * ----------------------
 *
 *   spec: flatmachine
 *   spec_version: "0.1.0"
 *
 *   data:
 *     name: writer-critic-loop
 *
 *     context:
 *       product: "{{ input.product }}"
 *       score: 0
 *       round: 0
 *
 *     agents:
 *       writer: ./writer.yml
 *       critic: ./critic.yml
 *
 *     states:
 *       start:
 *         type: initial
 *         transitions:
 *           - to: write
 *
 *       write:
 *         agent: writer
 *         execution:
 *           type: retry
 *           backoffs: [2, 8, 16, 35]
 *           jitter: 0.1
 *         on_error: error_state
 *         input:
 *           product: "{{ context.product }}"
 *         output_to_context:
 *           tagline: "{{ output.tagline }}"
 *         transitions:
 *           - to: review
 *
 *       review:
 *         agent: critic
 *         input:
 *           tagline: "{{ context.tagline }}"
 *         output_to_context:
 *           score: "{{ output.score }}"
 *           round: "{{ context.round + 1 }}"
 *         transitions:
 *           - condition: "context.score >= 8"
 *             to: done
 *           - to: write
 *
 *       done:
 *         type: final
 *         output:
 *           tagline: "{{ context.tagline }}"
 *           score: "{{ context.score }}"
 *
 *   metadata:
 *     description: "Iterative writer-critic loop"
 */

export interface MachineWrapper {
  spec: "flatmachine";
  spec_version: string;
  data: MachineData;
  metadata?: Record<string, any>;
}

export interface MachineData {
  name?: string;
  expression_engine?: "simple" | "cel";
  context?: Record<string, any>;
  agents?: Record<string, string | AgentWrapper>;
  states: Record<string, StateDefinition>;
  settings?: MachineSettings;
}

export interface MachineSettings {
  hooks?: string;  // Python module path
  max_steps?: number;
  [key: string]: any;
}

export interface StateDefinition {
  type?: "initial" | "final";
  agent?: string;
  action?: string;
  execution?: ExecutionConfig;
  on_error?: string | Record<string, string>;  // Simple: "error_state" or Granular: {default: "...", ErrorType: "..."}
  input?: Record<string, any>;
  output_to_context?: Record<string, string>;
  output?: Record<string, any>;
  transitions?: Transition[];
  tool_loop?: boolean;
  sampling?: "single" | "multi";
}

export interface ExecutionConfig {
  type: "default" | "retry" | "parallel" | "mdap_voting";
  // Retry config
  backoffs?: number[];  // Delay array in seconds, e.g., [2, 8, 16, 35]
  jitter?: number;      // Random variation factor, e.g., 0.1 for ±10%
  // Parallel config
  n_samples?: number;
  // MDAP voting config
  k_margin?: number;
  max_candidates?: number;
}

export interface Transition {
  condition?: string;
  to: string;
}

import { AgentWrapper, OutputSchema, ModelConfig } from "./flatagent";
export { AgentWrapper, OutputSchema };

export type FlatmachineConfig = MachineWrapper;
