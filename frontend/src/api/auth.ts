import { ApiError, requestJson, requestNoContent } from "./client";
import { asObject, readString } from "./parse";

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
