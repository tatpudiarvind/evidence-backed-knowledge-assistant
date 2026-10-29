import { requestJson } from "./client";
import {
  asObject,
  readArray,
  readBoolean,
  readEnum,
  readNumber,
  readOptionalEnum,
  readOptionalNumber,
  readOptionalString,
  readString,
} from "./parse";

/** The longest question the API accepts, once extra spaces are removed. */
export const MAX_QUESTION_LENGTH = 1000;

/** How long the API keeps a question and its answer. */
export const QUESTION_RETENTION_DAYS = 3;

export const ANSWER_MODES = ["generated", "search_only"] as const;

/** "generated": a model wrote the answer, or declined to. "search_only": no model wrote it. */
export type AnswerMode = (typeof ANSWER_MODES)[number];

export const ABSTENTION_REASONS = [
  "no_indexed_documents",
  "weak_evidence",
  "insufficient_evidence",
  "uncited_answer",
] as const;

export type AbstentionReason = (typeof ABSTENTION_REASONS)[number];

export type Citation = {
  /** The [n] marker in a generated answer's text. */
  number: number;
  documentId: string;
  documentName: string;
  chunkId: string;
  /** PDF pages, from 1. */
  pageNumber: number | null;
  /** The Word heading the passage falls under. */
  section: string | null;
  excerpt: string;
  /** Cosine similarity to the question; higher is closer. */
  similarity: number;
};

export type Answer = {
  mode: AnswerMode;
  /** Only a generated answer that doesn't abstain has text. */
  text: string | null;
  abstained: boolean;
  abstentionReason: AbstentionReason | null;
  /** The model that was asked, if one was. */
  modelName: string | null;
  citations: Citation[];
};

export type QuestionRecord = {
  id: string;
  workspaceId: string;
  text: string;
  createdAt: string;
  /** When the API deletes the question and its answer. */
  expiresAt: string;
  answer: Answer;
};

function parseCitation(value: unknown): Citation {
  const source = asObject(value);
  return {
    number: readNumber(source, "number"),
    documentId: readString(source, "document_id"),
    documentName: readString(source, "document_name"),
    chunkId: readString(source, "chunk_id"),
    pageNumber: readOptionalNumber(source, "page_number"),
    section: readOptionalString(source, "section"),
    excerpt: readString(source, "excerpt"),
    similarity: readNumber(source, "similarity"),
  };
}

function parseAnswer(value: unknown): Answer {
  const source = asObject(value);
  return {
    mode: readEnum(source, "mode", ANSWER_MODES),
    text: readOptionalString(source, "text"),
    abstained: readBoolean(source, "abstained"),
    abstentionReason: readOptionalEnum(source, "abstention_reason", ABSTENTION_REASONS),
    modelName: readOptionalString(source, "model_name"),
    citations: readArray(source, "citations").map(parseCitation),
  };
}

function parseQuestion(value: unknown): QuestionRecord {
  const source = asObject(value);
  return {
    id: readString(source, "id"),
    workspaceId: readString(source, "workspace_id"),
    text: readString(source, "text"),
    createdAt: readString(source, "created_at"),
    expiresAt: readString(source, "expires_at"),
    answer: parseAnswer(source.answer),
  };
}

function parseQuestionList(body: unknown): QuestionRecord[] {
  return readArray(asObject(body), "items").map(parseQuestion);
}

function questionsPath(workspaceId: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/questions`;
}

/** The caller's questions in a workspace from the last 3 days, newest first, at most 50. */
export function listQuestions(
  workspaceId: string,
  signal?: AbortSignal,
): Promise<QuestionRecord[]> {
  return requestJson(questionsPath(workspaceId), parseQuestionList, { signal });
}

/** Answers from the workspace's ready documents; a local model can take a minute or more. */
export function askQuestion(
  workspaceId: string,
  text: string,
  signal?: AbortSignal,
): Promise<QuestionRecord> {
  return requestJson(questionsPath(workspaceId), parseQuestion, {
    method: "POST",
    body: { text },
    signal,
  });
}
