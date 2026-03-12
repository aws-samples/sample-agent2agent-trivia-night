/**
 * Unit tests for Auth flow (using amazon-cognito-identity-js).
 * Requirements: 8.1, 8.2, 8.3, 8.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock amazon-cognito-identity-js
vi.mock('amazon-cognito-identity-js', () => {
  const mockGetSession = vi.fn();
  const mockAuthenticateUser = vi.fn();
  const mockSignOut = vi.fn();

  return {
    CognitoUserPool: vi.fn().mockImplementation(() => ({
      getCurrentUser: vi.fn().mockReturnValue(null),
    })),
    CognitoUser: vi.fn().mockImplementation(() => ({
      authenticateUser: mockAuthenticateUser,
      getSession: mockGetSession,
      signOut: mockSignOut,
    })),
    AuthenticationDetails: vi.fn(),
  };
});

// Mock AWS SDK
vi.mock('@aws-sdk/client-cognito-identity', () => ({
  CognitoIdentityClient: vi.fn(),
  GetIdCommand: vi.fn(),
  GetCredentialsForIdentityCommand: vi.fn(),
}));

import { AuthService } from '../../services/AuthService';

describe('AuthService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (AuthService as any).instance = undefined;

    (window as any).AWS_CONFIG = {
      region: 'us-east-1',
      userPoolId: 'us-east-1_testPool',
      userPoolWebClientId: 'testClientId',
      identityPoolId: 'us-east-1:test-identity-pool',
      apiGatewayUrl: 'https://api.example.com/prod',
      cognitoDomain: 'test.auth.us-east-1.amazoncognito.com',
    };
  });

  it('starts with unauthenticated state when no current user', () => {
    const service = AuthService.getInstance();
    const state = service.getAuthState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.loading).toBe(false);
  });

  it('subscribe allows listening to auth state changes', () => {
    const service = AuthService.getInstance();
    const listener = vi.fn();
    const unsubscribe = service.subscribe(listener);
    expect(typeof unsubscribe).toBe('function');
    unsubscribe();
  });

  it('signOut resets auth state', () => {
    const service = AuthService.getInstance();
    service.signOut();
    const state = service.getAuthState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
  });

  it('isAuthenticated returns false when no session', async () => {
    const service = AuthService.getInstance();
    const result = await service.isAuthenticated();
    expect(result).toBe(false);
  });

  it('getCurrentUser returns null when not authenticated', async () => {
    const service = AuthService.getInstance();
    const user = await service.getCurrentUser();
    expect(user).toBeNull();
  });
});
