/**
 * FlatAgents JavaScript SDK
 * Reference implementation of the FlatAgents spec.
 */

export const VERSION = "0.1.0";

// TODO: Implement DeclarativeAgent
export class DeclarativeAgent {
  constructor(config: AgentConfig | string) {
    throw new Error("Not implemented yet");
  }

  async execute(input: Record<string, unknown>): Promise<unknown> {
    throw new Error("Not implemented yet");
  }
}

// Types based on declarative-agent.d.ts spec
export interface AgentConfig {
  spec: "declarative_agent";
  spec_version: string;
  data: AgentData;
  metadata?: Record<string, unknown>;
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
