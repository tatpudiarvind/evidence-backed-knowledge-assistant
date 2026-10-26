export type ReadinessResponse = {
  status: "ok";
  database: "ok";
};

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

function isReadinessResponse(value: unknown): value is ReadinessResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const response = value as Record<string, unknown>;
  return response.status === "ok" && response.database === "ok";
}

export async function getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  const response = await fetch(`${apiBaseUrl}/health/ready`, { signal });
  if (!response.ok) {
    throw new Error("The local API is not ready.");
  }

  const body: unknown = await response.json();
  if (!isReadinessResponse(body)) {
    throw new Error("The local API returned an unexpected readiness response.");
  }

  return body;
}
