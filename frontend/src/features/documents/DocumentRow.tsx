import { type KeyboardEvent, useEffect, useRef, useState } from "react";

import { ApiError, isUnauthenticated } from "../../api/client";
import {
  type DocumentRecord,
  type DocumentStatus,
  deleteDocument,
  downloadDocument,
} from "../../api/documents";
import ErrorNotice from "../../components/ErrorNotice";
import { fileTypeLabel, formatDateTime, formatFileSize } from "./format";
import { saveBlob } from "./saveBlob";

const STATUS_LABELS: Record<DocumentStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
  deleting: "Deleting",
};

const STATUS_TONES: Record<DocumentStatus, string> = {
  queued: "pending",
  processing: "pending",
  ready: "ready",
  failed: "failed",
  deleting: "neutral",
};

type Activity = "idle" | "downloading" | "confirming" | "deleting";

type DocumentRowProps = {
  record: DocumentRecord;
  onDeleted: (record: DocumentRecord) => void;
  onChanged: (record: DocumentRecord) => void;
  onSessionExpired: () => void;
};

export default function DocumentRow({
  record,
  onDeleted,
  onChanged,
  onSessionExpired,
}: DocumentRowProps) {
  const [activity, setActivity] = useState<Activity>("idle");
  const [error, setError] = useState<unknown>(null);
  const deleteButtonRef = useRef<HTMLButtonElement>(null);
  const keepButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef(false);

  useEffect(() => {
    if (activity === "confirming") {
      keepButtonRef.current?.focus();
    } else if (activity === "idle" && returnFocusRef.current) {
      returnFocusRef.current = false;
      deleteButtonRef.current?.focus();
    }
  }, [activity]);

  async function handleDownload() {
    setActivity("downloading");
    setError(null);
    try {
      saveBlob(await downloadDocument(record.id), record.displayName);
      setActivity("idle");
    } catch (caught) {
      if (isUnauthenticated(caught)) {
        onSessionExpired();
        return;
      }
      setError(caught);
      setActivity("idle");
    }
  }

  function askToDelete() {
    setError(null);
    setActivity("confirming");
  }

  function keepDocument() {
    returnFocusRef.current = true;
    setActivity("idle");
  }

  function handleConfirmKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && activity === "confirming") {
      event.preventDefault();
      keepDocument();
    }
  }

  async function handleDelete() {
    setActivity("deleting");
    try {
      await deleteDocument(record.id);
      onDeleted(record);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        // Already gone, perhaps deleted from another tab.
        onDeleted(record);
        return;
      }
      if (isUnauthenticated(caught)) {
        onSessionExpired();
        return;
      }
      if (caught instanceof ApiError && caught.code === "document_delete_failed") {
        onChanged({ ...record, status: "deleting" });
      }
      setError(caught);
      returnFocusRef.current = true;
      setActivity("idle");
    }
  }

  const confirming = activity === "confirming" || activity === "deleting";
  const hiddenName = <span className="visually-hidden"> {record.displayName}</span>;

  return (
    <li className="document-row">
      <span className="file-tile" aria-hidden="true">
        {fileTypeLabel(record.mimeType, record.displayName)}
      </span>
      <div className="document-main">
        <p className="document-name" title={record.displayName}>
          {record.displayName}
        </p>
        <p className="document-meta">
          {formatFileSize(record.sizeBytes)}
          <span aria-hidden="true"> · </span>
          <span className="visually-hidden">, </span>
          Added <time dateTime={record.createdAt}>{formatDateTime(record.createdAt)}</time>
        </p>
        {record.status === "failed" && record.failureMessage && (
          <p className="document-failure">{record.failureMessage}</p>
        )}
      </div>
      <span className={`status-badge status-${STATUS_TONES[record.status]}`}>
        <span className="status-dot" aria-hidden="true" />
        {STATUS_LABELS[record.status]}
      </span>
      <div className="document-actions">
        {confirming ? (
          <div
            className="confirm-delete"
            role="group"
            aria-label={`Delete ${record.displayName}?`}
            onKeyDown={handleConfirmKeyDown}
          >
            <span className="confirm-text">Delete permanently?</span>
            <button
              type="button"
              className="button button-danger button-small"
              onClick={handleDelete}
              disabled={activity === "deleting"}
            >
              {activity === "deleting" ? "Deleting…" : "Delete"}
              {hiddenName}
            </button>
            <button
              ref={keepButtonRef}
              type="button"
              className="button button-quiet button-small"
              onClick={keepDocument}
              disabled={activity === "deleting"}
            >
              Keep
            </button>
          </div>
        ) : (
          <>
            <button
              type="button"
              className="button button-secondary button-small"
              onClick={handleDownload}
              disabled={activity === "downloading" || record.status === "deleting"}
            >
              {activity === "downloading" ? "Downloading…" : "Download"}
              {hiddenName}
            </button>
            <button
              ref={deleteButtonRef}
              type="button"
              className="button button-quiet button-small"
              onClick={askToDelete}
              disabled={activity === "downloading"}
            >
              Delete
              {hiddenName}
            </button>
          </>
        )}
      </div>
      {error !== null && (
        <div className="document-error">
          <ErrorNotice error={error} />
        </div>
      )}
    </li>
  );
}
