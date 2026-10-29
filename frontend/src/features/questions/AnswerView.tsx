import { Fragment } from "react";

import type { AbstentionReason, Answer, QuestionRecord } from "../../api/questions";
import { formatDateTime } from "../documents/format";
import { splitAnswer } from "./answerText";
import SourceItem from "./SourceItem";

type Message = { title: string; detail: string };

const ABSTENTION_MESSAGES: Record<AbstentionReason, Message> = {
  no_indexed_documents: {
    title: "No documents were ready to search.",
    detail: "Add a document, wait until it's Ready, then ask again.",
  },
  weak_evidence: {
    title: "No passage matched the question closely enough.",
    detail: "Try other words, or add a document that covers it.",
  },
  insufficient_evidence: {
    title: "The closest passages don't contain the answer.",
    detail: "The model said so instead of guessing. Try other words, or add a document that covers it.",
  },
  uncited_answer: {
    title: "The model's reply didn't cite its sources.",
    detail: "Answers must point to the passages they come from, so this one isn't shown. Try asking again.",
  },
};

const UNKNOWN_ABSTENTION: Message = {
  title: "No answer was found.",
  detail: "Try other words, or add a document that covers it.",
};

export function abstentionMessage(reason: AbstentionReason | null): Message {
  return reason === null ? UNKNOWN_ABSTENTION : ABSTENTION_MESSAGES[reason];
}

/** The id of a listed source, which the answer's [n] links point to. */
function sourceAnchor(questionId: string, number: number): string {
  return `source-${questionId}-${number}`;
}

function AnswerText({ questionId, answer }: { questionId: string; answer: Answer }) {
  const citations = new Map(answer.citations.map((citation) => [citation.number, citation]));
  return (
    <p className="answer-text">
      {splitAnswer(answer.text ?? "", citations).map((part, index) =>
        part.kind === "text" ? (
          <Fragment key={index}>{part.text}</Fragment>
        ) : (
          <a
            key={index}
            className="citation-ref"
            href={`#${sourceAnchor(questionId, part.number)}`}
            aria-label={`Source ${part.number}, ${part.citation.documentName}`}
          >
            {/* Hidden brackets keep "[1]" in copied text. */}
            <span className="visually-hidden">[</span>
            {part.number}
            <span className="visually-hidden">]</span>
          </a>
        ),
      )}
    </p>
  );
}

function searchOnlyLead(answer: Answer): string {
  const reason =
    answer.modelName === null
      ? "No language model is set up"
      : `${answer.modelName} didn't reply`;
  return `${reason}, so these are the passages that best match the question.`;
}

type AnswerViewProps = {
  question: QuestionRecord;
  onSessionExpired: () => void;
};

export default function AnswerView({ question, onSessionExpired }: AnswerViewProps) {
  const { answer } = question;
  const searchOnly = answer.mode === "search_only";

  let body;
  if (answer.abstained) {
    const message = abstentionMessage(answer.abstentionReason);
    body = (
      <div className="answer-declined">
        <p className="answer-declined-title">{message.title}</p>
        <p>{message.detail}</p>
      </div>
    );
  } else if (searchOnly) {
    body = <p className="answer-lead">{searchOnlyLead(answer)}</p>;
  } else {
    body = (
      <>
        <AnswerText questionId={question.id} answer={answer} />
        <p className="answer-note">
          Written by {answer.modelName ?? "a language model"} from the sources below. Check them
          before relying on it; it isn't professional advice.
        </p>
      </>
    );
  }

  return (
    <div className="answer">
      {body}
      {answer.citations.length > 0 && (
        <div>
          <h4 className="sources-title">{searchOnly ? "Closest passages" : "Sources"}</h4>
          <ol className="source-list">
            {answer.citations.map((citation) => (
              <SourceItem
                key={citation.number}
                citation={citation}
                anchorId={sourceAnchor(question.id, citation.number)}
                showExcerpt={searchOnly}
                onSessionExpired={onSessionExpired}
              />
            ))}
          </ol>
        </div>
      )}
      <p className="answer-footer">
        Deleted automatically on{" "}
        <time dateTime={question.expiresAt}>{formatDateTime(question.expiresAt)}</time>.
      </p>
    </div>
  );
}
