/**
 * SigV4-signed HTTP client for the Backend API.
 *
 * Provides methods for all registry endpoints plus the chat endpoint.
 * Includes exponential-backoff retry for transient (5xx / network) failures.
 */

import { fromCognitoIdentityPool } from '@aws-sdk/credential-providers';
import { HttpRequest } from '@aws-sdk/protocol-http';
import { SignatureV4 } from '@aws-sdk/signature-v4';
import { Sha256 } from '@aws-crypto/sha256-js';
import type { AgentCard } from '../types/AgentCard';
import type { SearchResult, PaginatedResponse, ChatResponse } from '../types/AgentCard';

/* ------------------------------------------------------------------ */
/*  Config & error types                                               */
/* ------------------------------------------------------------------ */

export interface AgentRegistryClientConfig {
  apiGatewayUrl: string;
  region?: string;
  identityPoolId?: string;
  maxRetries?: number;
}

export class AgentRegistryError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public code?: string,
  ) {
    super(message);
    this.name = 'AgentRegistryError';
  }
}

/* ------------------------------------------------------------------ */
/*  Client                                                             */
/* ------------------------------------------------------------------ */

export class AgentRegistryClient {
  private apiGatewayUrl: string;
  private region: string;
  private maxRetries: number;
  private signer?: SignatureV4;

  constructor(config: AgentRegistryClientConfig) {
    this.apiGatewayUrl = config.apiGatewayUrl.replace(/\/$/, '');
    this.region = config.region || 'us-east-1';
    this.maxRetries = config.maxRetries ?? 3;

    if (config.identityPoolId) {
      const credentials = fromCognitoIdentityPool({
        identityPoolId: config.identityPoolId,
        clientConfig: { region: this.region },
      });

      this.signer = new SignatureV4({
        credentials,
        region: this.region,
        service: 'execute-api',
        sha256: Sha256,
      });
    }
  }

  /** Refresh the SigV4 signer with new credentials (e.g. after login) */
  async updateCredentials(credentials: any): Promise<void> {
    this.signer = new SignatureV4({
      credentials: () => Promise.resolve(credentials),
      region: this.region,
      service: 'execute-api',
      sha256: Sha256,
    });
  }

  /* ---------------------------------------------------------------- */
  /*  Internal HTTP helpers                                            */
  /* ---------------------------------------------------------------- */

  private isRetryable(error: any): boolean {
    if (error instanceof AgentRegistryError && error.statusCode && error.statusCode >= 500) return true;
    if (error.name === 'NetworkError' || error.name === 'TimeoutError') return true;
    return false;
  }

  private retryDelay(attempt: number): number {
    const base = 1000 * Math.pow(2, attempt);
    return base + Math.random() * base * 0.1;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((r) => setTimeout(r, ms));
  }

  private async makeRequest<T>(
    method: string,
    path: string,
    body?: any,
    params?: Record<string, string>,
  ): Promise<T> {
    const url = new URL(`${this.apiGatewayUrl}${path}`);
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.append(k, v));
    }

    let requestInit: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    };

    // SigV4 sign when not going through a local proxy
    const isProxy = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
    if (this.signer && !isProxy) {
      const parsed = new URL(url.toString());
      const httpReq = new HttpRequest({
        method,
        protocol: parsed.protocol,
        hostname: parsed.hostname,
        port: parsed.port ? parseInt(parsed.port) : undefined,
        path: parsed.pathname,
        query: Object.fromEntries(parsed.searchParams),
        headers: {
          ...(requestInit.headers as Record<string, string>),
          host: parsed.hostname,
        },
        body: requestInit.body as string | undefined,
      });

      const signed = await this.signer.sign(httpReq, {
        signingDate: new Date(),
        signingRegion: this.region,
        signingService: 'execute-api',
      });

      requestInit = { method: signed.method, headers: signed.headers, body: signed.body };
    }

    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        const response = await fetch(url.toString(), requestInit);

        if (response.ok) {
          const ct = response.headers.get('content-type');
          if (ct && ct.includes('application/json')) return (await response.json()) as T;
          return { message: await response.text() } as T;
        }

        // Parse error body
        let errorMessage = `Request failed with status ${response.status}`;
        let errorCode = 'UNKNOWN_ERROR';
        try {
          const errData = await response.json();
          errorMessage = errData.message || errData.error?.message || errorMessage;
          errorCode = errData.error_code || errData.error?.code || errorCode;
        } catch { /* use defaults */ }

        const err = new AgentRegistryError(errorMessage, response.status, errorCode);

        // Only retry 5xx
        if (response.status >= 500 && attempt < this.maxRetries) {
          lastError = err;
          await this.sleep(this.retryDelay(attempt));
          continue;
        }
        throw err;
      } catch (error) {
        if (error instanceof AgentRegistryError) throw error;
        if (attempt < this.maxRetries && this.isRetryable(error)) {
          lastError = error as Error;
          await this.sleep(this.retryDelay(attempt));
          continue;
        }
        throw new AgentRegistryError(
          `Request failed: ${error instanceof Error ? error.message : 'Unknown error'}`,
        );
      }
    }

    throw new AgentRegistryError(
      `Request failed after ${this.maxRetries} retries: ${lastError?.message}`,
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Agent CRUD                                                       */
  /* ---------------------------------------------------------------- */

  async createAgent(agentCard: AgentCard): Promise<string> {
    const res = await this.makeRequest<{ agent_id: string }>('POST', '/agents', agentCard);
    return res.agent_id;
  }

  async getAgent(agentId: string): Promise<AgentCard> {
    const res = await this.makeRequest<{ agent: AgentCard }>('GET', `/agents/${agentId}`);
    return res.agent;
  }

  async listAgents(limit = 50, offset = 0): Promise<PaginatedResponse<AgentCard>> {
    const res = await this.makeRequest<{
      items?: AgentCard[];
      agents?: AgentCard[];
      pagination: { total: number; has_more: boolean; limit: number; offset: number };
    }>('GET', '/agents', undefined, { limit: String(limit), offset: String(offset) });

    return {
      items: res.items || res.agents || [],
      total: res.pagination?.total || 0,
      limit,
      offset,
      has_more: res.pagination?.has_more || false,
    };
  }

  async updateAgent(agentId: string, data: Partial<AgentCard>): Promise<boolean> {
    const res = await this.makeRequest<{ message: string }>('PUT', `/agents/${agentId}`, data);
    return res.message?.toLowerCase().includes('success') || false;
  }

  async deleteAgent(agentId: string): Promise<boolean> {
    const res = await this.makeRequest<{ message: string }>('DELETE', `/agents/${agentId}`);
    return res.message?.toLowerCase().includes('success') || false;
  }

  /* ---------------------------------------------------------------- */
  /*  Search                                                           */
  /* ---------------------------------------------------------------- */

  async searchAgents(query?: string, skills?: string[], topK = 10): Promise<SearchResult[]> {
    const params: Record<string, string> = {};
    if (query) params.query = query;
    if (skills?.length) params.skills = skills.join(',');

    const res = await this.makeRequest<SearchResult[] | { results: SearchResult[] }>(
      'GET',
      '/agents/search',
      undefined,
      params,
    );

    const results = Array.isArray(res) ? res : res.results || [];
    return results.map((r) => ({
      agent_id: r.agent_id || '',
      agent_card: r.agent_card,
      similarity_score: r.similarity_score || 0,
      matched_skills: r.matched_skills || [],
    }));
  }

  /* ---------------------------------------------------------------- */
  /*  Health check                                                     */
  /* ---------------------------------------------------------------- */

  async healthCheck(agentId: string): Promise<boolean> {
    const res = await this.makeRequest<{ message: string }>('POST', `/agents/${agentId}/health`);
    return res.message?.toLowerCase().includes('success') || false;
  }

  /* ---------------------------------------------------------------- */
  /*  Chat                                                             */
  /* ---------------------------------------------------------------- */

  async chat(agentId: string, message: string): Promise<ChatResponse> {
    return this.makeRequest<ChatResponse>('POST', '/chat', { agentId, message });
  }
}
