import { requestJson } from "./client";
import { asObject, readArray, readEnum, readString } from "./parse";

export const WORKSPACE_ROLES = ["owner", "member"] as const;

export type WorkspaceRole = (typeof WORKSPACE_ROLES)[number];

export type Workspace = {
  id: string;
  name: string;
  role: WorkspaceRole;
  createdAt: string;
};

function parseWorkspace(value: unknown): Workspace {
  const source = asObject(value);
  return {
    id: readString(source, "id"),
    name: readString(source, "name"),
    role: readEnum(source, "role", WORKSPACE_ROLES),
    createdAt: readString(source, "created_at"),
  };
}

function parseWorkspaceList(body: unknown): Workspace[] {
  return readArray(asObject(body), "items").map(parseWorkspace);
}

/** The signed-in user's workspaces, oldest first. */
export function listWorkspaces(signal?: AbortSignal): Promise<Workspace[]> {
  return requestJson("/api/v1/workspaces", parseWorkspaceList, { signal });
}

export function createWorkspace(name: string): Promise<Workspace> {
  return requestJson("/api/v1/workspaces", parseWorkspace, { method: "POST", body: { name } });
}
