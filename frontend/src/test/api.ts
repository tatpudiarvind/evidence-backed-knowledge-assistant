import { vi } from "vitest";

/** A route's response, or a function that builds one from the request. */
export type RouteHandler =
  | Response
  | ((request: { url: URL; init: RequestInit }) => Response | Promise<Response>);

/** Keys look like "GET /api/v1/workspaces". */
export type Routes = Record<string, RouteHandler>;

export type FetchCall = {
  key: string;
  init: RequestInit;
};

export const USER = { id: "user-1", email: "reader@example.com" };

export const READY_RESPONSE = jsonResponse({ status: "ok", database: "ok" });

export function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function emptyResponse(status = 204): Response {
  return new Response(null, { status });
}

export function apiErrorResponse(
  status: number,
  code: string,
  message: string,
  options: { requestId?: string; fields?: { location: string; message: string }[] } = {},
): Response {
  const error: Record<string, unknown> = {
    code,
    message,
    request_id: options.requestId ?? "req-test",
  };
  if (options.fields) {
    error.fields = options.fields;
  }
  return jsonResponse({ error }, status);
}

export function unauthenticatedResponse(): Response {
  return apiErrorResponse(401, "not_authenticated", "Sign in to continue.");
}

export function workspaceJson(overrides: Record<string, unknown> = {}) {
  return {
    id: "ws-1",
    name: "Product manuals",
    role: "owner",
    created_at: "2025-01-02T10:00:00Z",
    ...overrides,
  };
}

export function documentJson(overrides: Record<string, unknown> = {}) {
  return {
    id: "doc-1",
    workspace_id: "ws-1",
    display_name: "guide.pdf",
    mime_type: "application/pdf",
    size_bytes: 2048,
    sha256: "a".repeat(64),
    status: "queued",
    failure_code: null,
    failure_message: null,
    created_at: "2025-01-03T09:30:00Z",
    updated_at: "2025-01-03T09:30:00Z",
    ...overrides,
  };
}

export function citationJson(overrides: Record<string, unknown> = {}) {
  return {
    number: 1,
    document_id: "doc-1",
    document_name: "guide.pdf",
    chunk_id: "chunk-1",
    page_number: 3,
    section: null,
    excerpt: "New staff get 25 days of leave a year.",
    similarity: 0.71234,
    ...overrides,
  };
}

export const MODEL_NAME = "qwen3:4b-instruct-2507-q4_K_M";

export function answerJson(overrides: Record<string, unknown> = {}) {
  return {
    mode: "generated",
    text: "New staff get 25 days of leave [1].",
    abstained: false,
    abstention_reason: null,
    model_name: MODEL_NAME,
    citations: [citationJson()],
    ...overrides,
  };
}

export function questionJson(
  overrides: Record<string, unknown> = {},
  answer: Record<string, unknown> = {},
) {
  return {
    id: "q-1",
    workspace_id: "ws-1",
    text: "How much leave do new staff get?",
    created_at: "2025-01-04T09:00:00Z",
    expires_at: "2025-01-07T09:00:00Z",
    answer: answerJson(answer),
    ...overrides,
  };
}

/**
 * Replaces fetch with a router keyed by method and path. Tests can change `routes` later to
 * simulate the API changing between requests. Unknown routes get a 501 error response.
 */
export function installFetch(routes: Routes) {
  const calls: FetchCall[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${(init.method ?? "GET").toUpperCase()} ${url.pathname}`;
    calls.push({ key, init });
    if (init.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }
    const handler = routes[key];
    if (!handler) {
      return apiErrorResponse(501, "no_test_route", `No test route for ${key}.`);
    }
    const response = typeof handler === "function" ? await handler({ url, init }) : handler;
    // Static responses are reused, and a body can only be read once.
    return response.clone();
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, routes };
}

export function callsTo(calls: FetchCall[], key: string): FetchCall[] {
  return calls.filter((call) => call.key === key);
}

export function jsonBody(call: FetchCall | undefined): unknown {
  return JSON.parse(String(call?.init.body));
}

/**
 * Reads a blob from a test response. On Node 22, fetch returns Node's own Blob, which has text()
 * but which jsdom's FileReader rejects; on Node 24 it returns jsdom's Blob, which has no text().
 */
export function readBlobText(blob: Blob): Promise<string> {
  if (typeof (blob as Partial<Blob>).text === "function") {
    return blob.text();
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("The blob couldn't be read."));
    reader.readAsText(blob);
  });
}
