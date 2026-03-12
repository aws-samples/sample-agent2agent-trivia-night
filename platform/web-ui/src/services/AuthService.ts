/**
 * Auth service using amazon-cognito-identity-js directly.
 * No Amplify, no hosted UI redirects — just straightforward
 * username/password authentication with Cognito User Pool.
 */
import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
} from 'amazon-cognito-identity-js';
import { CognitoIdentityClient, GetIdCommand, GetCredentialsForIdentityCommand } from '@aws-sdk/client-cognito-identity';

interface AWSConfig {
  region: string;
  userPoolId: string;
  userPoolWebClientId: string;
  identityPoolId: string;
  apiGatewayUrl: string;
  cognitoDomain: string;
}

const getAWSConfig = (): AWSConfig => {
  if (typeof window !== 'undefined' && (window as any).AWS_CONFIG) {
    const config = (window as any).AWS_CONFIG;
    if (config.userPoolId && !config.userPoolId.includes('PLACEHOLDER')) {
      return config;
    }
  }
  return {
    region: import.meta.env.VITE_AWS_REGION || 'us-east-1',
    userPoolId: import.meta.env.VITE_USER_POOL_ID || '',
    userPoolWebClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID || '',
    identityPoolId: import.meta.env.VITE_IDENTITY_POOL_ID || '',
    apiGatewayUrl: import.meta.env.VITE_API_GATEWAY_URL || '',
    cognitoDomain: import.meta.env.VITE_COGNITO_DOMAIN || '',
  };
};

export interface AuthState {
  isAuthenticated: boolean;
  user: CognitoUser | null;
  loading: boolean;
  error: string | null;
}

export interface AWSCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken: string;
}

export class AuthService {
  private static instance: AuthService;
  private userPool: CognitoUserPool;
  private config: AWSConfig;
  private authState: AuthState = {
    isAuthenticated: false,
    user: null,
    loading: true,
    error: null,
  };
  private listeners: ((state: AuthState) => void)[] = [];

  private constructor() {
    this.config = getAWSConfig();
    this.userPool = new CognitoUserPool({
      UserPoolId: this.config.userPoolId,
      ClientId: this.config.userPoolWebClientId,
    });
    this.checkSession();
  }

  static getInstance(): AuthService {
    if (!AuthService.instance) {
      AuthService.instance = new AuthService();
    }
    return AuthService.instance;
  }

  /* ---- State management ---- */

  private updateAuthState(newState: Partial<AuthState>) {
    this.authState = { ...this.authState, ...newState };
    this.listeners.forEach((fn) => fn(this.authState));
  }

  subscribe(listener: (state: AuthState) => void): () => void {
    this.listeners.push(listener);
    return () => {
      const idx = this.listeners.indexOf(listener);
      if (idx > -1) this.listeners.splice(idx, 1);
    };
  }

  getAuthState(): AuthState {
    return { ...this.authState };
  }

  /* ---- Check existing session ---- */

  private checkSession() {
    const currentUser = this.userPool.getCurrentUser();
    if (!currentUser) {
      this.updateAuthState({ isAuthenticated: false, user: null, loading: false, error: null });
      return;
    }
    currentUser.getSession((err: any, session: CognitoUserSession | null) => {
      if (err || !session || !session.isValid()) {
        this.updateAuthState({ isAuthenticated: false, user: null, loading: false, error: null });
      } else {
        this.updateAuthState({ isAuthenticated: true, user: currentUser, loading: false, error: null });
      }
    });
  }

  /* ---- Sign in ---- */

  signIn(username: string, password: string): Promise<CognitoUser> {
    return new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({
        Username: username,
        Pool: this.userPool,
      });
      const authDetails = new AuthenticationDetails({
        Username: username,
        Password: password,
      });

      cognitoUser.authenticateUser(authDetails, {
        onSuccess: () => {
          this.updateAuthState({ isAuthenticated: true, user: cognitoUser, loading: false, error: null });
          resolve(cognitoUser);
        },
        onFailure: (err) => {
          this.updateAuthState({ isAuthenticated: false, user: null, loading: false, error: err.message });
          reject(err);
        },
        newPasswordRequired: (userAttributes) => {
          // For workshop: auto-complete the new password challenge
          // Remove non-writable attributes
          delete userAttributes.email_verified;
          delete userAttributes.phone_number_verified;
          cognitoUser.completeNewPasswordChallenge(password, userAttributes, {
            onSuccess: () => {
              this.updateAuthState({ isAuthenticated: true, user: cognitoUser, loading: false, error: null });
              resolve(cognitoUser);
            },
            onFailure: (err) => {
              this.updateAuthState({ isAuthenticated: false, user: null, loading: false, error: err.message });
              reject(err);
            },
          });
        },
      });
    });
  }

  /* ---- Sign out ---- */

  signOut(): void {
    const currentUser = this.userPool.getCurrentUser();
    if (currentUser) {
      currentUser.signOut();
    }
    this.updateAuthState({ isAuthenticated: false, user: null, loading: false, error: null });
  }

  /* ---- Get session / tokens ---- */

  getSession(): Promise<CognitoUserSession> {
    return new Promise((resolve, reject) => {
      const currentUser = this.userPool.getCurrentUser();
      if (!currentUser) {
        reject(new Error('No current user'));
        return;
      }
      currentUser.getSession((err: any, session: CognitoUserSession | null) => {
        if (err || !session) {
          reject(err || new Error('No session'));
        } else {
          resolve(session);
        }
      });
    });
  }

  /* ---- Get AWS credentials from Identity Pool ---- */

  async getCredentials(): Promise<AWSCredentials> {
    const session = await this.getSession();
    const idToken = session.getIdToken().getJwtToken();
    const providerKey = `cognito-idp.${this.config.region}.amazonaws.com/${this.config.userPoolId}`;

    const client = new CognitoIdentityClient({ region: this.config.region });

    const { IdentityId } = await client.send(new GetIdCommand({
      IdentityPoolId: this.config.identityPoolId,
      Logins: { [providerKey]: idToken },
    }));

    const { Credentials } = await client.send(new GetCredentialsForIdentityCommand({
      IdentityId: IdentityId!,
      Logins: { [providerKey]: idToken },
    }));

    return {
      accessKeyId: Credentials!.AccessKeyId!,
      secretAccessKey: Credentials!.SecretKey!,
      sessionToken: Credentials!.SessionToken!,
    };
  }

  async isAuthenticated(): Promise<boolean> {
    try {
      const session = await this.getSession();
      return session.isValid();
    } catch {
      return false;
    }
  }

  async getCurrentUser(): Promise<CognitoUser | null> {
    return this.userPool.getCurrentUser();
  }

  configure(): void { /* no-op for compatibility */ }
  redirectToLogin(): void { /* no-op — we use inline login form */ }
  signInWithHostedUI(): void { /* no-op */ }
  getHostedUIUrl(): string { return ''; }
  getHostedUILogoutUrl(): string { return ''; }
}

export default AuthService;
