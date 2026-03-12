/**
 * Singleton API client factory.
 *
 * Creates an AgentRegistryClient that gets SigV4 credentials
 * from AuthService (which uses the Cognito ID token to get
 * Identity Pool credentials).
 */

import { AgentRegistryClient } from './AgentRegistryClient';
import AuthService from './AuthService';

let client: AgentRegistryClient | null = null;
let credentialsReady: Promise<void> | null = null;

export function getApiClient(): AgentRegistryClient {
  if (client) return client;

  const cfg = (window as any).AWS_CONFIG ?? {};
  client = new AgentRegistryClient({
    apiGatewayUrl: cfg.apiGatewayUrl || '',
    region: cfg.region || 'us-east-1',
  });

  // Start credential refresh immediately
  credentialsReady = refreshClientCredentials();

  return client;
}

/**
 * Wait for credentials to be ready before making API calls.
 * Call this in components before the first API request.
 */
export async function ensureCredentials(): Promise<void> {
  if (!client) getApiClient();
  if (credentialsReady) await credentialsReady;
}

async function refreshClientCredentials(): Promise<void> {
  try {
    const creds = await AuthService.getInstance().getCredentials();
    if (client) {
      await client.updateCredentials({
        accessKeyId: creds.accessKeyId,
        secretAccessKey: creds.secretAccessKey,
        sessionToken: creds.sessionToken,
      });
    }
  } catch (err) {
    console.error('Failed to get AWS credentials for API client:', err);
  }
}

/** Call this after login to refresh the client's credentials */
export async function refreshApiClientCredentials(): Promise<void> {
  client = null;
  credentialsReady = null;
  getApiClient();
  if (credentialsReady) await credentialsReady;
}
