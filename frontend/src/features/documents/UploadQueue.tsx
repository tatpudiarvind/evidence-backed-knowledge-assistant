import { useId } from "react";

import ErrorNotice from "../../components/ErrorNotice";
import { formatFileSize } from "./format";

export type UploadState = "waiting" | "uploading" | "done" | "failed";

export type UploadItem = {
  id: number;
  file: File;
  state: UploadState;
  error: unknown;
};

const STATE_LABELS: Record<UploadState, string> = {
  waiting: "Waiting",
  uploading: "Uploading…",
  done: "Added",
  failed: "Not added",
};

type UploadQueueProps = {
  items: UploadItem[];
  onClear: () => void;
};

export function isUploadActive(item: UploadItem): boolean {
  return item.state === "waiting" || item.state === "uploading";
}

export default function UploadQueue({ items, onClear }: UploadQueueProps) {
  const id = useId();
  const finished = items.filter((item) => !isUploadActive(item)).length;
  const added = items.filter((item) => item.state === "done").length;
  const active = finished < items.length;
  const summary = `${added} of ${items.length} ${items.length === 1 ? "file" : "files"} added.`;

  return (
    <section className="upload-queue" aria-labelledby={`${id}-title`}>
      <div className="upload-queue-header">
        <h3 id={`${id}-title`}>Uploads</h3>
        <span className="upload-progress">
          {finished} of {items.length} finished
        </span>
        {!active && (
          <button type="button" className="button-link" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      {active && <p className="upload-hint">Keep this workspace open until uploads finish.</p>}
      <p className="visually-hidden" role="status">
        {active ? "" : summary}
      </p>
      <ul className="upload-list">
        {items.map((item) => (
          <li key={item.id} className={`upload-item upload-${item.state}`}>
            <div className="upload-line">
              <span className="upload-name" title={item.file.name}>
                {item.file.name}
              </span>
              <span className="upload-size">{formatFileSize(item.file.size)}</span>
              <span className="upload-state">{STATE_LABELS[item.state]}</span>
            </div>
            {item.state === "failed" && <ErrorNotice error={item.error} live={false} />}
          </li>
        ))}
      </ul>
    </section>
  );
}
