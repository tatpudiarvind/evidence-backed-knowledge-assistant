import { useState } from "react";

import { isUnauthenticated } from "../../api/client";
import { downloadDocument } from "../../api/documents";
import type { Citation } from "../../api/questions";
import ErrorNotice from "../../components/ErrorNotice";
import { saveBlob } from "../documents/saveBlob";

const similarityFormat = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

type SourceItemProps = {
  citation: Citation;
  /** The element id that the answer's [n] links point to. */
  anchorId: string;
  /** Show the passage straight away, as when the passages are the answer. */
  showExcerpt: boolean;
  onSessionExpired: () => void;
};

/** Where the passage is in its document: a PDF page or a Word heading. Text files have neither. */
function sourceLocation(citation: Citation): string | null {
  if (citation.pageNumber !== null) {
    return `Page ${citation.pageNumber}`;
  }
  return citation.section === null ? null : `Section: ${citation.section}`;
}

export default function SourceItem({
  citation,
  anchorId,
  showExcerpt,
  onSessionExpired,
}: SourceItemProps) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const location = sourceLocation(citation);

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      saveBlob(await downloadDocument(citation.documentId), citation.documentName);
    } catch (caught) {
      if (isUnauthenticated(caught)) {
        onSessionExpired();
        return;
      }
      setError(caught);
    }
    setDownloading(false);
  }

  return (
    <li id={anchorId} className="source-item">
      <span className="source-number" aria-hidden="true">
        {citation.number}
      </span>
      <div className="source-main">
        <p className="source-name" title={citation.documentName}>
          <span className="visually-hidden">Source {citation.number}: </span>
          {citation.documentName}
        </p>
        <p className="source-meta">
          {location !== null && (
            <>
              {location}
              <span aria-hidden="true"> · </span>
              <span className="visually-hidden">, </span>
            </>
          )}
          Similarity {similarityFormat.format(citation.similarity)}
        </p>
      </div>
      <button
        type="button"
        className="button button-secondary button-small"
        onClick={handleDownload}
        disabled={downloading}
      >
        {downloading ? "Downloading…" : "Download"}
        <span className="visually-hidden"> {citation.documentName}</span>
      </button>
      <details className="source-excerpt" open={showExcerpt}>
        <summary>Passage</summary>
        <blockquote>{citation.excerpt}</blockquote>
      </details>
      {error !== null && (
        <div className="source-error">
          <ErrorNotice error={error} />
        </div>
      )}
    </li>
  );
}
