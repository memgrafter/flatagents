/**
 * DeclarativeAgent Configuration Schema v0.4.0
 * =============================================
 *
 * An agent is a single LLM call: model + prompts + output schema.
 * Workflows handle composition, branching, and loops.
 *
 * STRUCTURE:
 * ----------
 * spec           - Fixed string "declarative_agent"
 * spec_version   - Semver string (e.g., "0.4.0")
 * data           - The agent configuration
 * metadata       - Extensibility layer (runners ignore unrecognized keys)
 *
 * DATA FIELDS:
 * ------------
 * name               - Agent identifier (inferred from filename if omitted)
 * model              - LLM configuration
 * system             - System prompt (Jinja2 template)
 * user               - User prompt template (Jinja2)
 * instruction_suffix - Optional instruction appended after user prompt
 * output             - Output schema (what fields we want)
 *
 * MODEL FIELDS:
 * -------------
 * name              - Model name (e.g., "gpt-4", "zai-glm-4.6")
 * provider          - Provider name (e.g., "openai", "anthropic", "cerebras")
 * temperature       - Sampling temperature (0.0 to 2.0)
 * max_tokens        - Maximum tokens to generate
 * top_p             - Nucleus sampling parameter
 * frequency_penalty - Frequency penalty (-2.0 to 2.0)
 * presence_penalty  - Presence penalty (-2.0 to 2.0)
 *
 * OUTPUT FIELD DEFINITION:
 * ------------------------
 * type        - Field type: str, int, float, bool, json, list, object
 * description - Description (used for structured output / tool calls)
 * enum        - Allowed values (for enum-like fields)
 * required    - Whether the field is required (default: true)
 * items       - For list type: the type of items
 * properties  - For object type: nested properties
 *
 * TEMPLATE SYNTAX:
 * ----------------
 * Prompts use Jinja2 templating. Available variables:
 *   - input.*  - Values passed to the agent at runtime
 *
 * Example: "Question: {{ input.question }}"
 *
 * EXAMPLE CONFIGURATION:
 * ----------------------
 *
 *   spec: declarative_agent
 *   spec_version: "0.4.0"
 *
 *   data:
 *     name: critic
 *
 *     model:
 *       provider: cerebras
 *       name: zai-glm-4.6
 *       temperature: 0.5
 *
 *     system: |
 *       Act as a ruthless critic. Analyze drafts for errors.
 *       Rate severity as: High, Medium, or Low.
 *
 *     user: |
 *       Question: {{ input.question }}
 *       Draft: {{ input.draft }}
 *
 *     output:
 *       critique:
 *         type: str
 *         description: "Specific errors found in the draft"
 *       severity:
 *         type: str
 *         description: "Error severity"
 *         enum: ["High", "Medium", "Low"]
 *
 *   metadata:
 *     description: "Critiques draft answers"
 *     tags: ["reflection", "qa"]
 */

export interface AgentWrapper {
  spec: "declarative_agent";
  spec_version: string;
  data: AgentData;
  metadata?: Record<string, any>;
}

export interface AgentData {
  name?: string;
  model: ModelConfig;
  system: string;
  user: string;
  instruction_suffix?: string;
  output?: OutputSchema;
}

export interface ModelConfig {
  name: string;
  provider?: string;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  frequency_penalty?: number;
  presence_penalty?: number;
}

export type OutputSchema = Record<string, OutputFieldDef>;

export interface OutputFieldDef {
  type: "str" | "int" | "float" | "bool" | "json" | "list" | "object";
  description?: string;
  enum?: string[];
  required?: boolean;
  items?: OutputFieldDef;
  properties?: OutputSchema;
}

export type DeclarativeAgentConfig = AgentWrapper;
