/**
 * DeclarativeAgent Configuration Schema v0.4.0
 * =============================================
 *
 * An agent is a single LLM call: model + prompts + output schema.
 * Workflows handle composition, branching, and loops.
 *
 * STRUCTURE (Container Architecture):
 * -----------------------------------
 * 1. spec         - Fixed string "declarative_agent"
 * 2. spec_version - Semver string (e.g., "0.4.0")
 * 3. data         - The agent configuration
 * 4. metadata     - Extensibility layer
 *
 * DATA SECTIONS:
 * --------------
 * - name          - Agent identifier
 * - model         - LLM configuration
 * - system        - System prompt (Jinja2 template)
 * - user          - User prompt template (Jinja2)
 * - output        - Output schema (what fields we want)
 *
 * TEMPLATE SYNTAX:
 * ----------------
 * Prompts use Jinja2 templating. Available variables:
 *   - input.*  - Values passed to the agent at runtime
 *
 * Example: "Question: {{ input.question }}"
 *
 * OUTPUT SCHEMA:
 * --------------
 * Declares the expected output fields. The runtime/extractor
 * decides HOW to extract (structured output, tool calls, regex, etc.)
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

// =============================================================================
// WRAPPER LAYER
// =============================================================================

/**
 * The top-level container for a declarative agent spec.
 */
export interface AgentWrapper {
  /**
   * Fixed string identifying this as a declarative agent spec.
   */
  spec: "declarative_agent";

  /**
   * Semver version of the spec this file adheres to.
   */
  spec_version: string;

  /**
   * The agent configuration.
   */
  data: AgentData;

  /**
   * Extensibility layer. Runners MUST ignore keys they don't recognize.
   */
  metadata?: Record<string, any>;
}

// =============================================================================
// DATA LAYER
// =============================================================================

/**
 * The agent configuration.
 * An agent is a single LLM call: model + prompts + output schema.
 */
export interface AgentData {
  /**
   * Agent identifier. Inferred from filename if omitted.
   */
  name?: string;

  /**
   * LLM model configuration.
   */
  model: ModelConfig;

  /**
   * System prompt defining the agent's role and constraints.
   * Supports Jinja2 templating with {{ input.* }} variables.
   */
  system: string;

  /**
   * User prompt template.
   * Supports Jinja2 with {{ input.* }} variables.
   */
  user: string;

  /**
   * Optional instruction appended after the user prompt.
   */
  instruction_suffix?: string;

  /**
   * Output schema - declares expected output fields.
   * The runtime/extractor decides how to extract these.
   */
  output?: OutputSchema;
}

/**
 * Model configuration.
 */
export interface ModelConfig {
  /**
   * Model name (e.g., "gpt-4", "zai-glm-4.6").
   */
  name: string;

  /**
   * Provider name (e.g., "openai", "anthropic", "cerebras").
   */
  provider?: string;

  /**
   * Sampling temperature (0.0 to 2.0).
   */
  temperature?: number;

  /**
   * Maximum tokens to generate.
   */
  max_tokens?: number;

  /**
   * Nucleus sampling parameter.
   */
  top_p?: number;

  /**
   * Frequency penalty (-2.0 to 2.0).
   */
  frequency_penalty?: number;

  /**
   * Presence penalty (-2.0 to 2.0).
   */
  presence_penalty?: number;
}

/**
 * Output schema - map of field names to field definitions.
 * Declares WHAT we want, not HOW to extract it.
 */
export type OutputSchema = Record<string, OutputFieldDef>;

/**
 * Output field definition.
 */
export interface OutputFieldDef {
  /**
   * Field type.
   */
  type: "str" | "int" | "float" | "bool" | "json" | "list" | "object";

  /**
   * Description of the field (used for structured output / tool calls).
   */
  description?: string;

  /**
   * Allowed values (for enum-like fields).
   */
  enum?: string[];

  /**
   * Whether the field is required.
   * @default true
   */
  required?: boolean;

  /**
   * For list type: the type of items.
   */
  items?: OutputFieldDef;

  /**
   * For object type: nested properties.
   */
  properties?: OutputSchema;
}

// =============================================================================
// MAIN EXPORT
// =============================================================================

/**
 * The declarative agent config type.
 */
export type DeclarativeAgentConfig = AgentWrapper;
