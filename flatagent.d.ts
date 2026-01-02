/**
 * FlatAgents Configuration Schema v0.6.0
 * =============================================
 *
 * An agent is a single LLM call: model + prompts + output schema.
 * Workflows handle composition, branching, and loops.
 *
 * STRUCTURE:
 * ----------
 * spec           - Fixed string "flatagents"
 * spec_version   - Semver string (e.g., "0.1.0")
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
 * mcp                - Optional MCP (Model Context Protocol) configuration
 *
 * MCP FIELDS:
 * -----------
 * servers            - Map of server name to MCPServerDef
 * tool_filter        - Optional allow/deny lists using "server:tool" format
 * tool_prompt        - Jinja2 template for tool prompt (uses {{ tools }} variable)
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
 *   spec: flatagents 
 *   spec_version: "0.6.0"
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
 *
 * MCPCONFIG:
 * ----------
 * MCP (Model Context Protocol) configuration.
 * Defines MCP servers and tool filtering rules.
 *   servers     - MCP server definitions, keyed by server name
 *   tool_filter - Optional tool filtering rules
 *   tool_prompt - Jinja2 template for tool prompt injection.
 *                 Available variables: tools (list of discovered tools)
 *                 Example: "{% for tool in tools %}{{ tool.name }}: {{ tool.description }}{% endfor %}"
 *
 * MCPSERVERDEF:
 * -------------
 * MCP server definition.
 * Supports stdio transport (command) or HTTP transport (server_url).
 * Stdio transport:
 *   command - Command to start the MCP server (e.g., "npx", "python")
 *   args    - Arguments for the command
 *   env     - Environment variables for the server process
 * HTTP transport:
 *   server_url - Base URL of the MCP server (e.g., "http://localhost:8000")
 *   headers    - HTTP headers (e.g., for authentication)
 *   timeout    - Request timeout in seconds
 *
 * TOOLFILTER:
 * -----------
 * Tool filtering rules using "server:tool" format.
 * Supports wildcards: "server:*" matches all tools from a server.
 *   allow - Tools to allow (if specified, only these are included)
 *   deny  - Tools to deny (takes precedence over allow)
 */

export const SPEC_VERSION = "0.6.0";

export interface AgentWrapper {
  spec: "flatagent";
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
  mcp?: MCPConfig;
}

export interface MCPConfig {
  servers: Record<string, MCPServerDef>;
  tool_filter?: ToolFilter;
  tool_prompt: string;
}

export interface MCPServerDef {
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  server_url?: string;
  headers?: Record<string, string>;
  timeout?: number;
}

export interface ToolFilter {
  allow?: string[];
  deny?: string[];
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

export type FlatagentsConfig = AgentWrapper;
