import { type FormEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

import { isUnauthenticated } from "../../api/client";
import {
  MAX_QUESTION_LENGTH,
  QUESTION_RETENTION_DAYS,
  type QuestionRecord,
  askQuestion,
  listQuestions,
} from "../../api/questions";
import type { Workspace } from "../../api/workspaces";
import ErrorNotice from "../../components/ErrorNotice";
import { formatDateTime } from "../documents/format";
import AnswerView, { abstentionMessage } from "./AnswerView";

type History =
  | { state: "loading" }
  | { state: "error"; error: unknown }
  | { state: "loaded"; questions: QuestionRecord[] };

export type QuestionPanelProps = {
  workspace: Workspace;
  /** How many documents are ready to search, or null until the document list loads. */
  readyCount: number | null;
  /** Documents deleted here. The API deletes the questions whose answers cite them. */
  deletedDocumentIds: ReadonlySet<string>;
  onSessionExpired: () => void;
};

/** Questions listed before "Show all". */
const FIRST_SHOWN = 5;
/** The count of characters left appears once this few remain. */
const LOW_CHARACTERS = 100;

const OUTCOMES = {
  answered: { label: "Answered", tone: "ready" },
  passages: { label: "Passages only", tone: "neutral" },
  declined: { label: "Not answered", tone: "pending" },
} as const;

function outcomeOf(question: QuestionRecord) {
  const { answer } = question;
  if (answer.abstained) {
    return OUTCOMES.declined;
  }
  return answer.mode === "generated" ? OUTCOMES.answered : OUTCOMES.passages;
}

function plural(count: number, noun: string): string {
  return count === 1 ? `1 ${noun}` : `${count} ${noun}s`;
}

function announcementFor(question: QuestionRecord): string {
  const { answer } = question;
  if (answer.abstained) {
    return `Not answered. ${abstentionMessage(answer.abstentionReason).title}`;
  }
  const count = answer.citations.length;
  return answer.mode === "generated"
    ? `Answered, citing ${plural(count, "source")}.`
    : `No answer was written. Found ${plural(count, "passage")} that match the question.`;
}

function citesAny(question: QuestionRecord, documentIds: ReadonlySet<string>): boolean {
  return question.answer.citations.some((citation) => documentIds.has(citation.documentId));
}

export default function QuestionPanel({
  workspace,
  readyCount,
  deletedDocumentIds,
  onSessionExpired,
}: QuestionPanelProps) {
  const [draft, setDraft] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<unknown>(null);
  const [history, setHistory] = useState<History>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [showAll, setShowAll] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const id = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const askAbortRef = useRef<AbortController | null>(null);
  const historyRef = useRef(history);
  // Questions answered here, oldest first. A list requested before one was answered may lack it.
  const askedRef = useRef<QuestionRecord[]>([]);
  const workspaceId = workspace.id;

  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  // A question still being answered when the panel closes is abandoned.
  useEffect(() => () => askAbortRef.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    const askedBefore = askedRef.current.length;
    listQuestions(workspaceId, controller.signal)
      .then((questions) => {
        const listed = new Set(questions.map((question) => question.id));
        const missing = askedRef.current
          .slice(askedBefore)
          .filter((question) => !listed.has(question.id))
          .reverse();
        setHistory({ state: "loaded", questions: [...missing, ...questions] });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (isUnauthenticated(error)) {
          onSessionExpired();
          return;
        }
        setHistory({ state: "error", error });
      });
    return () => controller.abort();
  }, [workspaceId, attempt, onSessionExpired]);

  // "Show all" disappears once used, so focus moves to the first question it revealed.
  useEffect(() => {
    if (showAll) {
      listRef.current?.querySelectorAll<HTMLElement>(".question-summary")[FIRST_SHOWN]?.focus();
    }
  }, [showAll]);

  const question = draft.trim();
  const noReadyDocuments = readyCount === 0;
  const canAsk = question !== "" && !asking && !noReadyDocuments;
  const remaining = MAX_QUESTION_LENGTH - draft.length;
  const showCount = remaining <= LOW_CHARACTERS;

  async function ask() {
    if (!canAsk) {
      return;
    }
    const sent = draft;
    const controller = new AbortController();
    askAbortRef.current = controller;
    setAsking(true);
    setAskError(null);
    setAnnouncement("Finding an answer…");
    try {
      const record = await askQuestion(workspaceId, question, controller.signal);
      askedRef.current.push(record);
      // Keep anything typed while waiting.
      setDraft((current) => (current === sent ? "" : current));
      if (historyRef.current.state === "error") {
        // Loading the list again picks up this question too.
        setHistory({ state: "loading" });
        setAttempt((value) => value + 1);
      } else {
        // A list still loading adds the question itself if the API's reply lacks it.
        setHistory((current) =>
          current.state === "loaded"
            ? {
                state: "loaded",
                questions: [record, ...current.questions.filter((item) => item.id !== record.id)],
              }
            : current,
        );
      }
      setAnnouncement(announcementFor(record));
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      if (isUnauthenticated(error)) {
        onSessionExpired();
        return;
      }
      setAnnouncement("");
      setAskError(error);
    }
    setAsking(false);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void ask();
    }
  }

  function retryHistory() {
    setHistory({ state: "loading" });
    setAttempt((value) => value + 1);
  }

  const visible =
    history.state === "loaded"
      ? history.questions.filter((item) => !citesAny(item, deletedDocumentIds))
      : [];
  const shown = showAll ? visible : visible.slice(0, FIRST_SHOWN);

  return (
    <section className="library-section question-panel" aria-labelledby={`${id}-ask`}>
      <h2 id={`${id}-ask`}>Ask a question</h2>
      <p className="section-note">
        Answers use only this workspace's Ready documents and cite them. If the documents don't
        cover a question, you'll be told instead of getting a guess.
      </p>
      <form className="question-form" onSubmit={handleSubmit}>
        <textarea
          className="text-input question-input"
          aria-labelledby={`${id}-ask`}
          aria-describedby={showCount ? `${id}-hint ${id}-count` : `${id}-hint`}
          placeholder="What would you like to know from these documents?"
          rows={3}
          maxLength={MAX_QUESTION_LENGTH}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="question-actions">
          {/* aria-disabled rather than disabled, so the button keeps focus while asking. */}
          <button
            type="submit"
            className={`button button-primary${canAsk ? "" : " is-disabled"}`}
            aria-disabled={canAsk ? undefined : true}
          >
            {asking ? "Asking…" : "Ask"}
          </button>
          <p id={`${id}-hint`} className="field-hint">
            {noReadyDocuments
              ? "You can ask once a document is Ready."
              : "Press Enter to ask, or Shift+Enter for a new line."}
          </p>
          {showCount && (
            <p id={`${id}-count`} className="question-count">
              {plural(remaining, "character")} left
            </p>
          )}
        </div>
      </form>
      {asking && (
        <p className="asking-status delayed-status">
          <span className="asking-dot" aria-hidden="true" />
          Searching the documents. A local model can take a minute or more to answer.
        </p>
      )}
      {askError !== null && (
        <div className="ask-error">
          <ErrorNotice error={askError} />
        </div>
      )}

      <div className="question-history">
        <h3>Recent questions</h3>
        <p className="section-note">
          Questions and answers are deleted after {QUESTION_RETENTION_DAYS} days, or sooner if you
          delete a document they cite.
        </p>
        {history.state === "loading" && (
          <>
            <p className="visually-hidden" role="status">
              Loading recent questions…
            </p>
            <div className="question-skeleton" aria-hidden="true">
              <span className="skeleton skeleton-question" />
              <span className="skeleton skeleton-question" />
            </div>
          </>
        )}
        {history.state === "error" && (
          <div className="inline-state">
            <ErrorNotice error={history.error} />
            <button type="button" className="button button-secondary" onClick={retryHistory}>
              Try again
            </button>
          </div>
        )}
        {history.state === "loaded" && visible.length === 0 && (
          <p className="history-empty">No questions in the last {QUESTION_RETENTION_DAYS} days.</p>
        )}
        {visible.length > 0 && (
          <ul ref={listRef} className="question-list">
            {shown.map((item, index) => {
              const outcome = outcomeOf(item);
              return (
                <li key={item.id}>
                  {/* The newest question opens; React leaves the others as the reader set them. */}
                  <details className="question-item" open={index === 0}>
                    <summary className="question-summary">
                      <span className="question-text">{item.text}</span>
                      <time className="question-time" dateTime={item.createdAt}>
                        {formatDateTime(item.createdAt)}
                      </time>
                      <span className={`status-badge status-${outcome.tone}`}>
                        <span className="status-dot" aria-hidden="true" />
                        {outcome.label}
                      </span>
                    </summary>
                    <AnswerView question={item} onSessionExpired={onSessionExpired} />
                  </details>
                </li>
              );
            })}
          </ul>
        )}
        {!showAll && visible.length > FIRST_SHOWN && (
          <button type="button" className="button-link question-more" onClick={() => setShowAll(true)}>
            Show all {visible.length}
          </button>
        )}
      </div>

      <p className="visually-hidden" role="status">
        {announcement}
      </p>
    </section>
  );
}
