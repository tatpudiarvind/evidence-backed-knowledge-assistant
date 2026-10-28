import { describe, expect, it, vi } from "vitest";

import {
  apiErrorResponse,
  callsTo,
  installFetch,
  jsonBody,
  jsonResponse,
  readBlobText,
} from "../test/api";
import { getCurrentUser } from "./auth";
import {
  ApiError,
  NETWORK_ERROR_MESSAGE,
  requestBlob,
  requestJson,
  requestNoContent,
} from "./client";
import { UPLOAD_INTERRUPTED_MESSAGE, uploadDocument } from "./documents";

const anyBody = (body: unknown) => body;

describe("API client", () => {
  it("sends cookies, and adds the CSRF header only to state-changing requests", async () => {
    const { calls } = installFetch({
      "GET /things": jsonResponse({ ok: true }),
      "POST /things": jsonResponse({ ok: true }, 201),
    });

    await requestJson("/things", anyBody);
    await requestJson("/things", anyBody, { method: "POST", body: { name: "Notes" } });

    const [get] = callsTo(calls, "GET /things");
    const [post] = callsTo(calls, "POST /things");
    expect(get?.init.credentials).toBe("include");
    expect(get?.init.headers).not.toHaveProperty("X-CSRF-Protection");
    expect(post?.init.credentials).toBe("include");
    expect(post?.init.headers).toMatchObject({
      "X-CSRF-Protection": "1",
      "Content-Type": "application/json",
    });
    expect(jsonBody(post)).toEqual({ name: "Notes" });
  });

  it("sends form data without forcing a Content-Type", async () => {
    const { calls } = installFetch({
      "POST /api/v1/workspaces/ws-1/documents": apiErrorResponse(
        409,
        "document_limit_reached",
        "Full.",
      ),
    });

    await expect(uploadDocument("ws-1", new File(["hi"], "notes.txt"))).rejects.toThrow("Full.");

    const [call] = calls;
    expect(call?.init.body).toBeInstanceOf(FormData);
    expect(call?.init.headers).not.toHaveProperty("Content-Type");
    expect((call?.init.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("reads the error contract, including field problems and the request ID", async () => {
    installFetch({
      "POST /things": apiErrorResponse(
        422,
        "validation_failed",
        "Some fields are missing or invalid.",
        {
          requestId: "req-42",
          fields: [{ location: "body.name", message: "Too long." }],
        },
      ),
    });

    const error = await requestJson("/things", anyBody, { method: "POST", body: {} }).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "validation_failed",
      message: "Some fields are missing or invalid.",
      requestId: "req-42",
      fields: [{ location: "body.name", message: "Too long." }],
    });
  });

  it("reports an unreachable API as a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(requestNoContent("/things")).rejects.toMatchObject({
      status: 0,
      code: "network_error",
      message: NETWORK_ERROR_MESSAGE,
    });
  });

  it("explains an upload that was cut off", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(uploadDocument("ws-1", new File(["hi"], "notes.txt"))).rejects.toMatchObject({
      code: "network_error",
      message: UPLOAD_INTERRUPTED_MESSAGE,
    });
  });

  it("falls back to the X-Request-ID header when an error isn't JSON", async () => {
    installFetch({
      "GET /things": new Response("Bad gateway", {
        status: 502,
        headers: { "X-Request-ID": "req-header" },
      }),
    });

    await expect(requestJson("/things", anyBody)).rejects.toMatchObject({
      status: 502,
      code: "unexpected_response",
      requestId: "req-header",
    });
  });

  it("rejects a successful response with the wrong shape", async () => {
    installFetch({ "GET /api/v1/auth/me": jsonResponse({ id: 7 }) });

    await expect(getCurrentUser()).rejects.toMatchObject({ code: "unexpected_response" });
  });

  it("treats a missing session as signed out", async () => {
    installFetch({
      "GET /api/v1/auth/me": apiErrorResponse(401, "not_authenticated", "Sign in to continue."),
    });

    await expect(getCurrentUser()).resolves.toBeNull();
  });

  it("returns file downloads as blobs", async () => {
    installFetch({ "GET /files/1": new Response("file body", { status: 200 }) });

    const blob = await requestBlob("/files/1");

    await expect(readBlobText(blob)).resolves.toBe("file body");
  });

  it("passes aborts through instead of reporting a network error", async () => {
    installFetch({ "GET /things": jsonResponse({}) });
    const controller = new AbortController();
    controller.abort();

    await expect(
      requestJson("/things", anyBody, { signal: controller.signal }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});
