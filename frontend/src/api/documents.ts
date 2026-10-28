import { ApiError, requestBlob, requestJson, requestNoContent } from "./client";
import {
  asObject,
  readArray,
  readEnum,
  readNumber,
  readOptionalString,
  readString,
} from "./parse";

export const DOCUMENT_STATUSES = ["queued", "processing", "ready", "failed", "deleting"] as const;

export type DocumentStatus = (typeof DOCUMENT_STATUSES)[number];

/** The file types the API accepts, for a file input's accept attribute. */
export const ACCEPTED_FILE_TYPES = ".pdf,.docx,.txt";

export const UPLOAD_INTERRUPTED_MESSAGE =
  "The upload didn't finish. Check that the API is running and that the file isn't over the " +
  "size limit, then try again.";

export type DocumentRecord = {
  id: string;
  workspaceId: string;
  displayName: string;
  mimeType: string;
  sizeBytes: number;
  sha256: string;
  status: DocumentStatus;
  failureCode: string | null;
  failureMessage: string | null;
  createdAt: string;
  updatedAt: string;
};

function parseDocument(value: unknown): DocumentRecord {
  const source = asObject(value);
  return {
    id: readString(source, "id"),
    workspaceId: readString(source, "workspace_id"),
    displayName: readString(source, "display_name"),
    mimeType: readString(source, "mime_type"),
    sizeBytes: readNumber(source, "size_bytes"),
    sha256: readString(source, "sha256"),
    status: readEnum(source, "status", DOCUMENT_STATUSES),
    failureCode: readOptionalString(source, "failure_code"),
    failureMessage: readOptionalString(source, "failure_message"),
    createdAt: readString(source, "created_at"),
    updatedAt: readString(source, "updated_at"),
  };
}

function parseDocumentList(body: unknown): DocumentRecord[] {
  return readArray(asObject(body), "items").map(parseDocument);
}

function workspaceDocumentsPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/documents`;
}

function documentPath(documentId: string): string {
  return `/api/v1/documents/${encodeURIComponent(documentId)}`;
}

/** A workspace's documents, newest first. */
export function listDocuments(
  workspaceId: string,
  signal?: AbortSignal,
): Promise<DocumentRecord[]> {
  return requestJson(workspaceDocumentsPath(workspaceId), parseDocumentList, { signal });
}

export async function uploadDocument(
  workspaceId: string,
  file: File,
  signal?: AbortSignal,
): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    return await requestJson(workspaceDocumentsPath(workspaceId), parseDocument, {
      method: "POST",
      body: form,
      signal,
    });
  } catch (error) {
    // A browser may report a rejected oversized upload as a dropped connection.
    if (error instanceof ApiError && error.code === "network_error") {
      throw new ApiError(0, "network_error", UPLOAD_INTERRUPTED_MESSAGE);
    }
    throw error;
  }
}

export function downloadDocument(documentId: string, signal?: AbortSignal): Promise<Blob> {
  return requestBlob(`${documentPath(documentId)}/file`, { signal });
}

export function deleteDocument(documentId: string): Promise<void> {
  return requestNoContent(documentPath(documentId), { method: "DELETE" });
}
