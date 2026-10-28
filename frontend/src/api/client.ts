import { ResponseShapeError, asObject, readArray, readOptionalString, readString } from "./parse";

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const CSRF_HEADER = "X-CSRF-Protection";
const REQUEST_ID_HEADER = "X-Request-ID";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export const NETWORK_ERROR_MESSAGE =
  "Can't reach the API. Check that it's running, then try again.";

function readApiBaseUrl(): string {
  const configured: unknown = import.meta.env.VITE_API_BASE_URL;
  const base =
    typeof configured === "string" && configured.trim() !== ""
      ? configured.trim()
      : DEFAULT_API_BASE_URL;
  return base.replace(/\/+$/, "");
}

export const apiBaseUrl = readApiBaseUrl();

export type FieldProblem = {
  location: string;
  message: string;
};

/** An error response from the API, or a failure to reach it (status 0). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly fields: FieldProblem[];

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string | null = null,
    fields: FieldProblem[] = [],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.fields = fields;
  }
}

export function isUnauthenticated(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

export type RequestOptions = {
  method?: "GET" | "POST" | "DELETE";
  /** Sent as JSON, or as multipart form data when it's a FormData. */
  body?: unknown;
  signal?: AbortSignal;
};

export async function requestJson<T>(
  path: string,
  parse: (body: unknown) => T,
  options: RequestOptions = {},
): Promise<T> {
  const response = await send(path, options);
  const body = await readBody(response, options.signal, () => response.json() as Promise<unknown>);
  try {
    return parse(body);
  } catch (error) {
    if (error instanceof ResponseShapeError) {
      throw unexpectedResponse(response);
    }
    throw error;
  }
}

export async function requestNoContent(path: string, options: RequestOptions = {}): Promise<void> {
  await send(path, options);
}

export async function requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const response = await send(path, options);
  return readBody(response, options.signal, () => response.blob());
}

async function send(
  path: string,
  { method = "GET", body, signal }: RequestOptions,
): Promise<Response> {
  const headers: Record<string, string> = {};
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    // The browser sets the multipart Content-Type, including its boundary.
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (UNSAFE_METHODS.has(method)) {
    headers[CSRF_HEADER] = "1";
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      method,
      headers,
      body: payload,
      credentials: "include",
      signal,
    });
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    throw new ApiError(0, "network_error", NETWORK_ERROR_MESSAGE);
  }

  if (!response.ok) {
    throw await toApiError(response, signal);
  }
  return response;
}

async function readBody<T>(
  response: Response,
  signal: AbortSignal | undefined,
  read: () => Promise<T>,
): Promise<T> {
  try {
    return await read();
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    if (error instanceof SyntaxError) {
      throw unexpectedResponse(response);
    }
    throw new ApiError(0, "network_error", NETWORK_ERROR_MESSAGE);
  }
}

async function toApiError(response: Response, signal: AbortSignal | undefined): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    return unexpectedResponse(response);
  }

  try {
    const detail = asObject(asObject(body).error);
    const fields =
      detail.fields === undefined || detail.fields === null
        ? []
        : readArray(detail, "fields").map((item) => {
            const field = asObject(item);
            return {
              location: readString(field, "location"),
              message: readString(field, "message"),
            };
          });
    return new ApiError(
      response.status,
      readString(detail, "code"),
      readString(detail, "message"),
      readOptionalString(detail, "request_id") ?? headerRequestId(response),
      fields,
    );
  } catch (error) {
    if (error instanceof ResponseShapeError) {
      return unexpectedResponse(response);
    }
    throw error;
  }
}

function unexpectedResponse(response: Response): ApiError {
  return new ApiError(
    response.status,
    "unexpected_response",
    `The API returned an unexpected response (HTTP ${response.status}).`,
    headerRequestId(response),
  );
}

function headerRequestId(response: Response): string | null {
  return response.headers.get(REQUEST_ID_HEADER);
}
