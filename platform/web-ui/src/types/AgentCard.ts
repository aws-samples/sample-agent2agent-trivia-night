// Re-export A2A Protocol types from @a2a-js/sdk for reference
export type {
  AgentCard as A2AAgentCard,
  AgentSkill as A2AAgentSkill,
  AgentCapabilities,
  AgentProvider,
} from '@a2a-js/sdk';

/**
 * Agent card type matching the Google A2A protocol spec.
 * Uses index signature to allow extra fields from the API.
 */
export interface AgentCard {
  name: string;
  description: string;
  url: string;
  version: string;
  capabilities: {
    streaming?: boolean;
    pushNotifications?: boolean;
    stateTransitionHistory?: boolean;
  };
  defaultInputModes: string[];
  defaultOutputModes: string[];
  skills: AgentSkill[];
  provider?: { organization: string; url: string };
  documentationUrl?: string;
  authentication?: { schemes: string[]; credentials?: string };
  [key: string]: any;
}

export interface AgentSkill {
  id: string;
  name: string;
  description: string;
  tags: string[];
  examples?: string[];
  inputModes?: string[];
  outputModes?: string[];
}

/** Agent record as stored in the registry */
export interface Agent {
  agent_id: string;
  agent_card: AgentCard;
  is_online: boolean;
  updated_at: string;
}

export interface SearchResult {
  agent_id: string;
  agent_card: AgentCard;
  similarity_score: number;
  matched_skills: string[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

/** Chat endpoint response */
export interface ChatResponse {
  agentId: string;
  response: string;
  agentName: string;
}
