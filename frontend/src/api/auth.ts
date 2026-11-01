import { ApiError, requestJson, requestNoContent } from "./client";
import { asObject, readBoolean, readOptionalString, readString } from "./parse";

export type User = {
  id: string;
  email: string;
};

export type Credentials = {
  email: string;
  password: string;
};

function parseUser(body: unknown): User {
  const source = asObject(body);
  return { id: readString(source, "id"), email: readString(source, "email") };
}

/** Creates an account and signs it in. */
export function register(credentials: Credentials): Promise<User> {
  return requestJson("/api/v1/auth/register", parseUser, { method: "POST", body: credentials });
}

export function signIn(credentials: Credentials): Promise<User> {
  return requestJson("/api/v1/auth/login", parseUser, { method: "POST", body: credentials });
}

export function signOut(): Promise<void> {
  return requestNoContent("/api/v1/auth/logout", { method: "POST" });
}

export type AuthOptions = {
  /** Whether email-and-password sign-in is on. */
  password: boolean;
  registration: boolean;
  /** The name of the identity provider the server signs people in through, if it has one. */
  providerName: string | null;
};

/** What to use when the server can't be asked: the local sign-in every install has. */
export const DEFAULT_AUTH_OPTIONS: AuthOptions = {
  password: true,
  registration: true,
  providerName: null,
};

function parseAuthOptions(body: unknown): AuthOptions {
  const source = asObject(body);
  return {
    password: readBoolean(source, "password"),
    registration: readBoolean(source, "registration"),
    providerName: readOptionalString(source, "provider_name"),
  };
}

export function getAuthOptions(signal?: AbortSignal): Promise<AuthOptions> {
  return requestJson("/api/v1/auth/options", parseAuthOptions, { signal });
}

/** Where the browser goes to sign in through the identity provider. */
export function providerSignInUrl(returnTo: string): string {
  return `/api/v1/auth/oidc/login?return_to=${encodeURIComponent(returnTo)}`;
}

/** The signed-in user, or null when this browser has no valid session. */
export async function getCurrentUser(signal?: AbortSignal): Promise<User | null> {
  try {
    return await requestJson("/api/v1/auth/me", parseUser, { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}
