import { requestJson } from "./client";
import { asObject, readString } from "./parse";

export type Readiness = {
  status: string;
  database: string;
};

function parseReadiness(body: unknown): Readiness {
  const source = asObject(body);
  return { status: readString(source, "status"), database: readString(source, "database") };
}

/** Resolves when the API and its database are ready, and rejects otherwise. */
export async function getReadiness(signal?: AbortSignal): Promise<Readiness> {
  const readiness = await requestJson("/health/ready", parseReadiness, { signal });
  if (readiness.status !== "ok" || readiness.database !== "ok") {
    throw new Error("The API reported that it isn't ready.");
  }
  return readiness;
}
