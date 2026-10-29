import {
  type ChangeEvent,
  type DragEvent as ReactDragEvent,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { isUnauthenticated } from "../../api/client";
import {
  ACCEPTED_FILE_TYPES,
  type DocumentRecord,
  isIndexing,
  listDocuments,
  uploadDocument,
} from "../../api/documents";
import type { Workspace } from "../../api/workspaces";
import ErrorNotice from "../../components/ErrorNotice";
import DocumentRow from "./DocumentRow";
import UploadQueue, { type UploadItem, isUploadActive } from "./UploadQueue";

type Load =
  | { state: "loading" }
  | { state: "error"; error: unknown }
  | { state: "loaded"; documents: DocumentRecord[] };

type DocumentLibraryProps = {
  workspace: Workspace;
  /** Move focus to the workspace heading when the library first appears. */
  focusHeading: boolean;
  onSessionExpired: () => void;
  /** How long to wait between status checks while documents are being indexed. */
  refreshIntervalMs?: number;
};

const REFRESH_INTERVAL_MS = 2500;

let nextUploadId = 1;

function documentCount(count: number): string {
  if (count === 0) {
    return "No documents yet";
  }
  return count === 1 ? "1 document" : `${count} documents`;
}

function carriesFiles(dataTransfer: DataTransfer | null): boolean {
  return dataTransfer !== null && Array.from(dataTransfer.types).includes("Files");
}

/** Describes the documents that finished indexing between two versions of the list. */
function indexingOutcome(before: DocumentRecord[], after: DocumentRecord[]): string {
  const wasIndexing = new Set(
    before.filter((item) => isIndexing(item.status)).map((item) => item.id),
  );
  return after
    .filter((item) => wasIndexing.has(item.id))
    .flatMap((item) => {
      if (item.status === "ready") {
        return [`${item.displayName} is ready.`];
      }
      return item.status === "failed" ? [`${item.displayName} couldn't be indexed.`] : [];
    })
    .join(" ");
}

export default function DocumentLibrary({
  workspace,
  focusHeading,
  onSessionExpired,
  refreshIntervalMs = REFRESH_INTERVAL_MS,
}: DocumentLibraryProps) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const id = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const listHeadingRef = useRef<HTMLHeadingElement>(null);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const abortRef = useRef<AbortController | null>(null);
  // Counts changes made here, so a refresh that was sent before one can be ignored.
  const changesRef = useRef(0);
  const documentsRef = useRef<DocumentRecord[]>([]);
  const workspaceId = workspace.id;

  useEffect(() => {
    if (focusHeading) {
      headingRef.current?.focus();
    }
  }, [focusHeading]);

  // Uploads still waiting when the library closes are cancelled.
  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    listDocuments(workspaceId, controller.signal)
      .then((documents) => setLoad({ state: "loaded", documents }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (isUnauthenticated(error)) {
          onSessionExpired();
          return;
        }
        setLoad({ state: "error", error });
      });
    return () => controller.abort();
  }, [workspaceId, attempt, onSessionExpired]);

  const loadedDocuments = load.state === "loaded" ? load.documents : null;
  const indexing = loadedDocuments?.some((item) => isIndexing(item.status)) ?? false;

  useEffect(() => {
    documentsRef.current = loadedDocuments ?? [];
  }, [loadedDocuments]);

  // While documents are being indexed, check their status again every few seconds.
  useEffect(() => {
    if (!indexing) {
      return;
    }
    const controller = new AbortController();
    let timer = 0;

    async function refresh() {
      const changes = changesRef.current;
      try {
        const documents = await listDocuments(workspaceId, controller.signal);
        // A list sent before an upload, retry, or delete here would undo that change.
        if (!controller.signal.aborted && changesRef.current === changes) {
          const outcome = indexingOutcome(documentsRef.current, documents);
          setLoad({ state: "loaded", documents });
          if (outcome !== "") {
            setAnnouncement(outcome);
          }
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        if (isUnauthenticated(error)) {
          onSessionExpired();
          return;
        }
        // Otherwise the last list stays up, and the next check tries again.
      }
      if (!controller.signal.aborted) {
        timer = window.setTimeout(refresh, refreshIntervalMs);
      }
    }

    timer = window.setTimeout(refresh, refreshIntervalMs);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [indexing, workspaceId, onSessionExpired, refreshIntervalMs]);

  // A file dropped outside the drop zone would otherwise replace the app.
  useEffect(() => {
    function blockFileDrop(event: DragEvent) {
      if (!event.defaultPrevented && carriesFiles(event.dataTransfer)) {
        event.preventDefault();
      }
    }
    window.addEventListener("dragover", blockFileDrop);
    window.addEventListener("drop", blockFileDrop);
    return () => {
      window.removeEventListener("dragover", blockFileDrop);
      window.removeEventListener("drop", blockFileDrop);
    };
  }, []);

  const updateUpload = useCallback((uploadId: number, change: Partial<UploadItem>) => {
    setUploads((items) =>
      items.map((item) => (item.id === uploadId ? { ...item, ...change } : item)),
    );
  }, []);

  async function runUpload(item: UploadItem) {
    const signal = abortRef.current?.signal;
    if (signal?.aborted) {
      return;
    }
    updateUpload(item.id, { state: "uploading" });
    try {
      const record = await uploadDocument(workspaceId, item.file, signal);
      updateUpload(item.id, { state: "done" });
      changesRef.current += 1;
      // A status check that finished first may already list the new document.
      setLoad((current) =>
        current.state === "loaded"
          ? {
              state: "loaded",
              documents: [record, ...current.documents.filter((other) => other.id !== record.id)],
            }
          : current,
      );
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      if (isUnauthenticated(error)) {
        onSessionExpired();
        return;
      }
      updateUpload(item.id, { state: "failed", error });
    }
  }

  function addFiles(files: File[]) {
    if (files.length === 0) {
      return;
    }
    const items = files.map<UploadItem>((file) => ({
      id: nextUploadId++,
      file,
      state: "waiting",
      error: null,
    }));
    setUploads((current) => (current.some(isUploadActive) ? [...current, ...items] : items));
    // One upload at a time keeps the API's memory use and the progress list predictable.
    for (const item of items) {
      queueRef.current = queueRef.current.then(() => runUpload(item));
    }
  }

  const canUpload = load.state === "loaded";

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    addFiles(files);
  }

  function handleDragOver(event: ReactDragEvent<HTMLDivElement>) {
    if (!canUpload || !carriesFiles(event.dataTransfer)) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDragging(true);
  }

  function handleDragLeave(event: ReactDragEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setDragging(false);
    }
  }

  function handleDrop(event: ReactDragEvent<HTMLDivElement>) {
    setDragging(false);
    if (!canUpload || !carriesFiles(event.dataTransfer)) {
      return;
    }
    event.preventDefault();
    addFiles(Array.from(event.dataTransfer.files));
  }

  const handleDeleted = useCallback((record: DocumentRecord) => {
    changesRef.current += 1;
    setLoad((current) =>
      current.state === "loaded"
        ? { state: "loaded", documents: current.documents.filter((item) => item.id !== record.id) }
        : current,
    );
    setAnnouncement(`Deleted ${record.displayName}.`);
    listHeadingRef.current?.focus();
  }, []);

  const handleChanged = useCallback((record: DocumentRecord, announcement?: string) => {
    changesRef.current += 1;
    setLoad((current) =>
      current.state === "loaded"
        ? {
            state: "loaded",
            documents: current.documents.map((item) => (item.id === record.id ? record : item)),
          }
        : current,
    );
    if (announcement !== undefined) {
      setAnnouncement(announcement);
    }
  }, []);

  function retry() {
    setLoad({ state: "loading" });
    setAttempt((value) => value + 1);
  }

  return (
    <>
      <header className="library-header">
        <h1 ref={headingRef} tabIndex={-1} className="library-title">
          {workspace.name}
        </h1>
        <p className="library-meta">
          {load.state === "loaded" ? documentCount(load.documents.length) : "\u00a0"}
        </p>
      </header>

      <section className="library-section" aria-labelledby={`${id}-add`}>
        <h2 id={`${id}-add`}>Add documents</h2>
        <div
          className={`drop-zone${dragging ? " is-dragging" : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <p className="drop-zone-text">Drop PDF, Word (.docx), or text (.txt) files here.</p>
          <input
            id={`${id}-files`}
            className="file-input visually-hidden"
            type="file"
            multiple
            accept={ACCEPTED_FILE_TYPES}
            disabled={!canUpload}
            onChange={handleFileChange}
          />
          <label
            htmlFor={`${id}-files`}
            className={`button button-primary${canUpload ? "" : " is-disabled"}`}
          >
            Choose files
          </label>
        </div>
        <p className="policy-note">
          Only add documents you're allowed to use. Don't add patient records or other confidential
          information.
        </p>
        {uploads.length > 0 && <UploadQueue items={uploads} onClear={() => setUploads([])} />}
      </section>

      <section className="library-section" aria-labelledby={`${id}-documents`}>
        <h2 id={`${id}-documents`} ref={listHeadingRef} tabIndex={-1}>
          Documents
        </h2>
        <p className="section-note">
          New documents are indexed in the background, and their status here updates on its own.
        </p>
        {load.state === "loading" && (
          <>
            <p className="visually-hidden" role="status">
              Loading documents…
            </p>
            <div className="document-skeleton" aria-hidden="true">
              <span className="skeleton skeleton-row" />
              <span className="skeleton skeleton-row" />
              <span className="skeleton skeleton-row" />
            </div>
          </>
        )}
        {load.state === "error" && (
          <div className="inline-state">
            <ErrorNotice error={load.error} />
            <button type="button" className="button button-secondary" onClick={retry}>
              Try again
            </button>
          </div>
        )}
        {load.state === "loaded" && load.documents.length === 0 && (
          <div className="empty-state">
            <p className="empty-title">This workspace is empty</p>
            <p>Add PDF, Word, or text files above. They'll be listed here.</p>
          </div>
        )}
        {load.state === "loaded" && load.documents.length > 0 && (
          <ul className="document-list">
            {load.documents.map((record) => (
              <DocumentRow
                key={record.id}
                record={record}
                onDeleted={handleDeleted}
                onChanged={handleChanged}
                onSessionExpired={onSessionExpired}
              />
            ))}
          </ul>
        )}
      </section>

      <p className="visually-hidden" role="status">
        {announcement}
      </p>
    </>
  );
}
