import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Workspace } from "../../api/workspaces";
import {
  apiErrorResponse,
  callsTo,
  documentJson,
  emptyResponse,
  installFetch,
  jsonResponse,
  readBlobText,
  unauthenticatedResponse,
} from "../../test/api";
import type { QuestionPanelProps } from "../questions/QuestionPanel";
import DocumentLibrary from "./DocumentLibrary";
import { saveBlob } from "./saveBlob";

vi.mock("./saveBlob", () => ({ saveBlob: vi.fn() }));

// The panel has its own tests; here it only shows what the library tells it.
vi.mock("../questions/QuestionPanel", () => ({
  default: ({ readyCount, deletedDocumentIds }: QuestionPanelProps) =>
    `Question panel: ${readyCount ?? "unknown"} ready, deleted ${
      [...deletedDocumentIds].join(" ") || "none"
    }`,
}));

const WORKSPACE: Workspace = {
  id: "ws-1",
  name: "Product manuals",
  role: "owner",
  createdAt: "2025-01-02T10:00:00Z",
};

const LIST = "GET /api/v1/workspaces/ws-1/documents";
const UPLOAD = "POST /api/v1/workspaces/ws-1/documents";
const DELETE = "DELETE /api/v1/documents/doc-1";
const RETRY = "POST /api/v1/documents/doc-1/retry";
const UNSUPPORTED = "Only PDF, Word (.docx), and plain-text (.txt) files can be uploaded.";
const NO_TEXT = "No readable text was found.";
/** Short enough that status-check tests don't wait long, long enough to stay cheap. */
const QUICK_REFRESH_MS = 20;

function renderLibrary(onSessionExpired = vi.fn(), refreshIntervalMs?: number) {
  render(
    <DocumentLibrary
      workspace={WORKSPACE}
      focusHeading={false}
      onSessionExpired={onSessionExpired}
      refreshIntervalMs={refreshIntervalMs}
    />,
  );
  return onSessionExpired;
}

function rowFor(name: string): HTMLElement {
  const row = screen.getByRole("button", { name: `Download ${name}` }).closest("li");
  if (!row) {
    throw new Error(`No row for ${name}.`);
  }
  return row;
}

function dropZone(): HTMLElement {
  const zone = screen.getByText(/^Drop PDF/).closest<HTMLElement>(".drop-zone");
  if (!zone) {
    throw new Error("The drop zone wasn't rendered.");
  }
  return zone;
}

/** Accepts .txt files and rejects anything else, recording the order files arrive in. */
function uploadRoute(uploaded: string[]) {
  return ({ init }: { init: RequestInit }) => {
    const file = (init.body as FormData).get("file") as File;
    uploaded.push(file.name);
    if (!file.name.endsWith(".txt")) {
      return apiErrorResponse(415, "unsupported_file_type", UNSUPPORTED);
    }
    return jsonResponse(
      documentJson({
        id: `doc-${file.name}`,
        display_name: file.name,
        mime_type: "text/plain",
        size_bytes: file.size,
      }),
      202,
    );
  };
}

function chooseFiles(files: File[]) {
  fireEvent.change(screen.getByLabelText("Choose files"), { target: { files } });
}

function listOf(...items: Record<string, unknown>[]): Response {
  return jsonResponse({ items: items.map((item) => documentJson(item)) });
}

const FAILED_SCAN = {
  display_name: "scan.pdf",
  status: "failed",
  failure_code: "no_text_found",
  failure_message: NO_TEXT,
};

function pause(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

beforeEach(() => {
  vi.mocked(saveBlob).mockReset();
});

describe("DocumentLibrary", () => {
  it("lists documents with their status and any failure reason", async () => {
    installFetch({
      [LIST]: jsonResponse({
        items: [
          documentJson({ status: "ready" }),
          documentJson({
            id: "doc-2",
            display_name: "scan.pdf",
            status: "failed",
            failure_code: "no_text",
            failure_message: "No readable text was found.",
          }),
          documentJson({
            id: "doc-3",
            display_name: "notes.txt",
            mime_type: "text/plain",
            size_bytes: 1,
          }),
        ],
      }),
    });

    renderLibrary();
    expect(screen.getByLabelText("Choose files")).toBeDisabled();

    const list = await screen.findByRole("list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("3 documents")).toBeInTheDocument();
    expect(screen.getByLabelText("Choose files")).toBeEnabled();
    expect(within(rowFor("guide.pdf")).getByText("Ready")).toBeInTheDocument();
    expect(within(rowFor("guide.pdf")).getByText("PDF")).toBeInTheDocument();
    expect(within(rowFor("scan.pdf")).getByText("Failed")).toBeInTheDocument();
    expect(within(rowFor("scan.pdf")).getByText("No readable text was found.")).toBeInTheDocument();
    expect(within(rowFor("notes.txt")).getByText("Queued")).toBeInTheDocument();
    expect(within(rowFor("notes.txt")).getByText(/^1 byte/)).toBeInTheDocument();
  });

  it("explains an empty workspace", async () => {
    installFetch({ [LIST]: jsonResponse({ items: [] }) });

    renderLibrary();

    expect(await screen.findByText("This workspace is empty")).toBeInTheDocument();
    expect(screen.getByText("No documents yet")).toBeInTheDocument();
  });

  it("uploads chosen files one at a time and reports each result", async () => {
    const uploaded: string[] = [];
    installFetch({ [LIST]: jsonResponse({ items: [] }), [UPLOAD]: uploadRoute(uploaded) });
    renderLibrary();
    await screen.findByText("This workspace is empty");

    chooseFiles([
      new File(["hello"], "notes.txt", { type: "text/plain" }),
      new File(["png"], "photo.png", { type: "image/png" }),
    ]);

    expect(await screen.findByText("1 of 2 files added.")).toBeInTheDocument();
    expect(uploaded).toEqual(["notes.txt", "photo.png"]);
    const queue = screen.getByRole("region", { name: "Uploads" });
    expect(within(queue).getByText("2 of 2 finished")).toBeInTheDocument();
    expect(within(queue).getByText("Added")).toBeInTheDocument();
    expect(within(queue).getByText("Not added")).toBeInTheDocument();
    expect(within(queue).getByText(UNSUPPORTED)).toBeInTheDocument();
    // Failures listed in the queue aren't announced as alerts on top of the summary.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download notes.txt" })).toBeInTheDocument();
    expect(screen.getByText("1 document")).toBeInTheDocument();

    fireEvent.click(within(queue).getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("region", { name: "Uploads" })).not.toBeInTheDocument();
  });

  it("accepts files dropped on the drop zone", async () => {
    const uploaded: string[] = [];
    installFetch({ [LIST]: jsonResponse({ items: [] }), [UPLOAD]: uploadRoute(uploaded) });
    renderLibrary();
    await screen.findByText("This workspace is empty");
    const zone = dropZone();
    const file = new File(["hello"], "dropped.txt", { type: "text/plain" });

    fireEvent.dragOver(zone, { dataTransfer: { types: ["Files"], files: [file] } });
    expect(zone).toHaveClass("is-dragging");
    fireEvent.drop(zone, { dataTransfer: { types: ["Files"], files: [file] } });
    expect(zone).not.toHaveClass("is-dragging");

    expect(await screen.findByText("1 of 1 file added.")).toBeInTheDocument();
    expect(uploaded).toEqual(["dropped.txt"]);
  });

  it("confirms before deleting and keeps focus in a sensible place", async () => {
    const { calls } = installFetch({
      [LIST]: jsonResponse({ items: [documentJson()] }),
      [DELETE]: emptyResponse(),
    });
    renderLibrary();

    fireEvent.click(await screen.findByRole("button", { name: "Delete guide.pdf" }));
    const keep = within(screen.getByRole("group", { name: "Delete guide.pdf?" })).getByRole(
      "button",
      { name: "Keep" },
    );
    expect(keep).toHaveFocus();
    fireEvent.click(keep);
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete guide.pdf" })).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "Delete guide.pdf" }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Keep" }), { key: "Escape" });
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete guide.pdf" })).toHaveFocus();
    expect(callsTo(calls, DELETE)).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Delete guide.pdf" }));
    fireEvent.click(
      within(screen.getByRole("group")).getByRole("button", { name: "Delete guide.pdf" }),
    );

    expect(await screen.findByText("Deleted guide.pdf.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Documents" })).toHaveFocus();
    expect(screen.getByText("This workspace is empty")).toBeInTheDocument();
    expect(screen.getByText("No documents yet")).toBeInTheDocument();
    expect(callsTo(calls, DELETE)).toHaveLength(1);
  });

  it("shows a document stuck in deletion and lets the user retry", async () => {
    const { routes } = installFetch({
      [LIST]: jsonResponse({ items: [documentJson({ status: "ready" })] }),
      [DELETE]: apiErrorResponse(
        500,
        "document_delete_failed",
        "The document couldn't be fully deleted. Try again.",
        { requestId: "req-del" },
      ),
    });
    renderLibrary();

    fireEvent.click(await screen.findByRole("button", { name: "Delete guide.pdf" }));
    fireEvent.click(
      within(screen.getByRole("group")).getByRole("button", { name: "Delete guide.pdf" }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The document couldn't be fully deleted. Try again.");
    expect(alert).toHaveTextContent("Reference req-del");
    expect(screen.getByText("Deleting")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download guide.pdf" })).toBeDisabled();
    // The row moves focus in an effect, which can run just after the alert appears.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Delete guide.pdf" })).toHaveFocus(),
    );

    routes[DELETE] = emptyResponse();
    fireEvent.click(screen.getByRole("button", { name: "Delete guide.pdf" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(
      within(screen.getByRole("group")).getByRole("button", { name: "Delete guide.pdf" }),
    );

    expect(await screen.findByText("Deleted guide.pdf.")).toBeInTheDocument();
  });

  it("tells the question panel which documents are ready and which were deleted", async () => {
    installFetch({
      [LIST]: listOf(
        { status: "ready" },
        { id: "doc-2", display_name: "manual.pdf", status: "ready" },
        { id: "doc-3", display_name: "scan.pdf", status: "failed", failure_message: NO_TEXT },
      ),
      [DELETE]: emptyResponse(),
    });
    renderLibrary();

    expect(screen.getByText("Question panel: unknown ready, deleted none")).toBeInTheDocument();
    expect(await screen.findByText("Question panel: 2 ready, deleted none")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete guide.pdf" }));
    fireEvent.click(
      within(screen.getByRole("group")).getByRole("button", { name: "Delete guide.pdf" }),
    );

    expect(await screen.findByText("Question panel: 1 ready, deleted doc-1")).toBeInTheDocument();
  });

  it("downloads a document under its original name", async () => {
    installFetch({
      [LIST]: jsonResponse({ items: [documentJson({ status: "ready" })] }),
      "GET /api/v1/documents/doc-1/file": new Response("%PDF-1.7 test", {
        headers: { "Content-Type": "application/pdf" },
      }),
    });
    renderLibrary();

    fireEvent.click(await screen.findByRole("button", { name: "Download guide.pdf" }));

    await waitFor(() => expect(saveBlob).toHaveBeenCalledTimes(1));
    const [blob, name] = vi.mocked(saveBlob).mock.calls[0] ?? [];
    expect(name).toBe("guide.pdf");
    expect(blob).toBeDefined();
    await expect(readBlobText(blob ?? new Blob())).resolves.toBe("%PDF-1.7 test");
    expect(screen.getByRole("button", { name: "Download guide.pdf" })).toBeEnabled();
  });

  it("explains a failed download", async () => {
    installFetch({
      [LIST]: jsonResponse({ items: [documentJson({ status: "ready" })] }),
      "GET /api/v1/documents/doc-1/file": apiErrorResponse(
        404,
        "document_file_missing",
        "The stored file for this document is missing.",
      ),
    });
    renderLibrary();

    fireEvent.click(await screen.findByRole("button", { name: "Download guide.pdf" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The stored file for this document is missing.",
    );
    expect(saveBlob).not.toHaveBeenCalled();
  });

  it("offers a retry when documents can't load", async () => {
    const { routes } = installFetch({
      [LIST]: apiErrorResponse(503, "database_unavailable", "The database isn't available."),
    });
    renderLibrary();

    expect(await screen.findByRole("alert")).toHaveTextContent("The database isn't available.");
    expect(screen.getByLabelText("Choose files")).toBeDisabled();
    routes[LIST] = jsonResponse({ items: [] });
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("This workspace is empty")).toBeInTheDocument();
  });

  it("reports an ended session from an upload", async () => {
    installFetch({ [LIST]: jsonResponse({ items: [] }), [UPLOAD]: unauthenticatedResponse() });
    const onSessionExpired = renderLibrary();
    await screen.findByText("This workspace is empty");

    chooseFiles([new File(["hello"], "notes.txt", { type: "text/plain" })]);

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });

  it("checks indexing documents until they finish and announces the outcome", async () => {
    const manual = { id: "doc-2", display_name: "manual.pdf", status: "ready" };
    const { calls, routes } = installFetch({ [LIST]: listOf({}, manual) });
    renderLibrary(vi.fn(), QUICK_REFRESH_MS);
    await screen.findByRole("list");
    const row = rowFor("guide.pdf");
    expect(within(row).getByText("Queued")).toBeInTheDocument();

    routes[LIST] = listOf({ status: "processing" }, manual);
    expect(await within(row).findByText("Processing")).toBeInTheDocument();

    routes[LIST] = listOf({ status: "ready" }, manual);
    expect(await screen.findByText("guide.pdf is ready.")).toBeInTheDocument();
    expect(within(row).getByText("Ready")).toBeInTheDocument();

    // Nothing is being indexed any more, so the checks stop.
    const checks = callsTo(calls, LIST).length;
    await pause(QUICK_REFRESH_MS * 5);
    expect(callsTo(calls, LIST)).toHaveLength(checks);
  });

  it("announces a document that couldn't be indexed and indexes it again on request", async () => {
    const { calls, routes } = installFetch({
      [LIST]: listOf({ display_name: "scan.pdf", status: "processing" }),
      [RETRY]: jsonResponse(documentJson({ display_name: "scan.pdf" }), 202),
    });
    renderLibrary(vi.fn(), QUICK_REFRESH_MS);
    await screen.findByRole("list");
    const row = rowFor("scan.pdf");

    routes[LIST] = listOf(FAILED_SCAN);
    expect(await screen.findByText("scan.pdf couldn't be indexed.")).toBeInTheDocument();
    expect(within(row).getByText("Failed")).toBeInTheDocument();
    expect(within(row).getByText(NO_TEXT)).toBeInTheDocument();

    routes[LIST] = listOf({ display_name: "scan.pdf", status: "ready" });
    fireEvent.click(within(row).getByRole("button", { name: "Retry scan.pdf" }));

    expect(await screen.findByText("Queued scan.pdf to be indexed again.")).toBeInTheDocument();
    expect(within(row).getByText("Queued")).toBeInTheDocument();
    expect(within(row).queryByText(NO_TEXT)).not.toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Retry scan.pdf" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Download scan.pdf" })).toHaveFocus(),
    );
    expect(callsTo(calls, RETRY)[0]?.init.headers).toMatchObject({ "X-CSRF-Protection": "1" });

    expect(await screen.findByText("scan.pdf is ready.")).toBeInTheDocument();
    expect(within(row).getByText("Ready")).toBeInTheDocument();
  });

  it("ignores a status check that was sent before a change made here", async () => {
    const uploaded: string[] = [];
    let answerCheck: (response: Response) => void = () => undefined;
    const pendingCheck = new Promise<Response>((resolve) => {
      answerCheck = resolve;
    });
    let checks = 0;
    const { calls, routes } = installFetch({
      [LIST]: () => (++checks === 1 ? listOf({}) : pendingCheck),
      [UPLOAD]: uploadRoute(uploaded),
    });
    renderLibrary(vi.fn(), QUICK_REFRESH_MS);
    await waitFor(() => expect(callsTo(calls, LIST)).toHaveLength(2));

    chooseFiles([new File(["hello"], "notes.txt", { type: "text/plain" })]);
    expect(await screen.findByRole("button", { name: "Download notes.txt" })).toBeInTheDocument();

    // The pending check was sent before the upload, so its list lacks notes.txt.
    routes[LIST] = apiErrorResponse(503, "database_unavailable", "The database isn't available.");
    answerCheck(listOf({ status: "ready" }));
    // A later check starts only once the one before it has finished.
    await waitFor(() => expect(callsTo(calls, LIST).length).toBeGreaterThan(3));

    expect(screen.getByRole("button", { name: "Download notes.txt" })).toBeInTheDocument();
    expect(within(rowFor("guide.pdf")).getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("2 documents")).toBeInTheDocument();
    // Failed checks leave the list as it was, without an error.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    routes[LIST] = listOf(
      { id: "doc-notes.txt", display_name: "notes.txt", mime_type: "text/plain" },
      { status: "ready" },
    );
    expect(await screen.findByText("guide.pdf is ready.")).toBeInTheDocument();
    expect(screen.getByText("2 documents")).toBeInTheDocument();
  });

  it("reports an ended session from a status check", async () => {
    let checks = 0;
    installFetch({ [LIST]: () => (++checks === 1 ? listOf({}) : unauthenticatedResponse()) });

    const onSessionExpired = renderLibrary(vi.fn(), QUICK_REFRESH_MS);

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });

  it("shows a retried document as ready when it was indexed after all", async () => {
    installFetch({
      [LIST]: listOf(FAILED_SCAN),
      [RETRY]: apiErrorResponse(409, "document_already_indexed", "This document is already indexed."),
    });
    renderLibrary();

    fireEvent.click(await screen.findByRole("button", { name: "Retry scan.pdf" }));

    expect(await screen.findByText("scan.pdf is ready.")).toBeInTheDocument();
    expect(within(rowFor("scan.pdf")).getByText("Ready")).toBeInTheDocument();
    expect(screen.queryByText(NO_TEXT)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Download scan.pdf" })).toHaveFocus(),
    );
  });

  it.each([
    {
      reason: "the document is being deleted",
      response: apiErrorResponse(409, "document_being_deleted", "This document is being deleted."),
      message: "This document is being deleted.",
      status: "Deleting",
      focused: "Delete scan.pdf",
    },
    {
      reason: "the database is unavailable",
      response: apiErrorResponse(503, "database_unavailable", "The database isn't available."),
      message: "The database isn't available.",
      status: "Failed",
      focused: "Retry scan.pdf",
    },
  ])("explains a retry that fails because $reason", async (example) => {
    installFetch({ [LIST]: listOf(FAILED_SCAN), [RETRY]: example.response });
    renderLibrary();

    fireEvent.click(await screen.findByRole("button", { name: "Retry scan.pdf" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(example.message);
    expect(within(rowFor("scan.pdf")).getByText(example.status)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: example.focused })).toHaveFocus(),
    );
  });

  it("reports an ended session from a retry", async () => {
    installFetch({ [LIST]: listOf(FAILED_SCAN), [RETRY]: unauthenticatedResponse() });
    const onSessionExpired = renderLibrary();

    fireEvent.click(await screen.findByRole("button", { name: "Retry scan.pdf" }));

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });
});
