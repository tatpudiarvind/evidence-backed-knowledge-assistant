import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Workspace } from "../../api/workspaces";
import {
  MODEL_NAME,
  apiErrorResponse,
  callsTo,
  citationJson,
  installFetch,
  jsonBody,
  jsonResponse,
  questionJson,
  readBlobText,
  unauthenticatedResponse,
} from "../../test/api";
import { formatDateTime } from "../documents/format";
import { saveBlob } from "../documents/saveBlob";
import QuestionPanel, { type QuestionPanelProps } from "./QuestionPanel";

vi.mock("../documents/saveBlob", () => ({ saveBlob: vi.fn() }));

const WORKSPACE: Workspace = {
  id: "ws-1",
  name: "Product manuals",
  role: "owner",
  createdAt: "2025-01-02T10:00:00Z",
};

const HISTORY = "GET /api/v1/workspaces/ws-1/questions";
const ASK = "POST /api/v1/workspaces/ws-1/questions";
const DOWNLOAD = "GET /api/v1/documents/doc-1/file";
const QUESTION = "How much leave do new staff get?";
const OLDER = "Who approves leave requests?";
const NO_QUESTIONS = "No questions in the last 3 days.";
const SECOND_PASSAGE = citationJson({
  number: 2,
  chunk_id: "chunk-2",
  page_number: 4,
  excerpt: "Managers approve leave requests.",
  similarity: 0.6,
});

function renderPanel(props: Partial<Omit<QuestionPanelProps, "onSessionExpired">> = {}) {
  const onSessionExpired = vi.fn();
  const panelProps: QuestionPanelProps = {
    workspace: WORKSPACE,
    readyCount: 1,
    deletedDocumentIds: new Set(),
    onSessionExpired,
    ...props,
  };
  const view = render(<QuestionPanel {...panelProps} />);
  return {
    onSessionExpired,
    unmount: view.unmount,
    rerender: (changes: Partial<QuestionPanelProps>) =>
      view.rerender(<QuestionPanel {...panelProps} {...changes} />),
  };
}

function listOf(...questions: Record<string, unknown>[]): Response {
  return jsonResponse({ items: questions });
}

/** A response the test sends later, to see what the panel shows while it waits. */
function deferred() {
  let resolve: (response: Response) => void = () => undefined;
  const promise = new Promise<Response>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

function questionBox(): HTMLElement {
  return screen.getByRole("textbox", { name: "Ask a question" });
}

function typeQuestion(text: string) {
  fireEvent.change(questionBox(), { target: { value: text } });
}

/** The listed question with this text; its answer is inside. */
function questionItem(text: string): HTMLDetailsElement {
  const item = screen.getByText(text, { selector: ".question-text" }).closest("details");
  if (!item) {
    throw new Error(`"${text}" isn't listed.`);
  }
  return item;
}

async function findQuestionItem(text: string): Promise<HTMLDetailsElement> {
  await screen.findByText(text, { selector: ".question-text" });
  return questionItem(text);
}

function listedQuestions(): string[] {
  return Array.from(document.querySelectorAll(".question-text"), (item) => item.textContent ?? "");
}

beforeEach(() => {
  vi.mocked(saveBlob).mockReset();
});

describe("QuestionPanel", () => {
  it("lists recent questions, newest first and open, with their outcomes", async () => {
    installFetch({
      [HISTORY]: listOf(
        questionJson(),
        questionJson(
          { id: "q-2", text: "Is parking free?" },
          { mode: "search_only", text: null, model_name: null },
        ),
        questionJson(
          { id: "q-3", text: OLDER },
          {
            mode: "search_only",
            text: null,
            abstained: true,
            abstention_reason: "weak_evidence",
            model_name: null,
            citations: [],
          },
        ),
      ),
    });
    renderPanel();

    const newest = await findQuestionItem(QUESTION);

    expect(listedQuestions()).toEqual([QUESTION, "Is parking free?", OLDER]);
    expect(newest).toHaveAttribute("open");
    expect(questionItem("Is parking free?")).not.toHaveAttribute("open");
    expect(questionItem(OLDER)).not.toHaveAttribute("open");
    expect(within(newest).getByText("Answered")).toBeInTheDocument();
    expect(within(questionItem("Is parking free?")).getByText("Passages only")).toBeInTheDocument();
    expect(within(questionItem(OLDER)).getByText("Not answered")).toBeInTheDocument();
  });

  it("shows a written answer with links to the sources it cites", async () => {
    installFetch({ [HISTORY]: listOf(questionJson()) });
    renderPanel();

    const item = await findQuestionItem(QUESTION);

    expect(within(item).getByText(/New staff/, { selector: ".answer-text" })).toHaveTextContent(
      "New staff get 25 days of leave [1].",
    );
    expect(within(item).getByRole("link", { name: "Source 1, guide.pdf" })).toHaveAttribute(
      "href",
      "#source-q-1-1",
    );
    expect(within(item).getByText(/^Written by/)).toHaveTextContent(
      `Written by ${MODEL_NAME} from the sources below.`,
    );
    expect(within(item).getByRole("heading", { name: "Sources" })).toBeInTheDocument();
    const source = document.getElementById("source-q-1-1");
    const similarity = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(0.71234);
    expect(source).toHaveTextContent("Source 1: guide.pdf");
    expect(source).toHaveTextContent("Page 3");
    expect(source).toHaveTextContent(`Similarity ${similarity}`);
    expect(within(item).getByText("Passage").closest("details")).not.toHaveAttribute("open");
    expect(within(item).getByText(/^Deleted automatically on/)).toHaveTextContent(
      `Deleted automatically on ${formatDateTime("2025-01-07T09:00:00Z")}.`,
    );
  });

  it.each([
    {
      reason: "no model is set up",
      modelName: null,
      lead: "No language model is set up, so these are the passages that best match the question.",
    },
    {
      reason: "the model didn't reply",
      modelName: MODEL_NAME,
      lead: `${MODEL_NAME} didn't reply, so these are the passages that best match the question.`,
    },
  ])("lists the closest passages when $reason", async ({ modelName, lead }) => {
    installFetch({
      [HISTORY]: listOf(
        questionJson(
          {},
          {
            mode: "search_only",
            text: null,
            model_name: modelName,
            citations: [citationJson(), SECOND_PASSAGE],
          },
        ),
      ),
    });
    renderPanel();

    const item = await findQuestionItem(QUESTION);

    expect(within(item).getByText(lead)).toBeInTheDocument();
    expect(within(item).getByText("Passages only")).toBeInTheDocument();
    expect(within(item).getByRole("heading", { name: "Closest passages" })).toBeInTheDocument();
    expect(within(item).queryByRole("link")).not.toBeInTheDocument();
    const passages = within(item).getAllByText("Passage");
    expect(passages).toHaveLength(2);
    for (const passage of passages) {
      expect(passage.closest("details")).toHaveAttribute("open");
    }
    expect(within(item).getByText("Managers approve leave requests.")).toBeInTheDocument();
  });

  it.each([
    { reason: "no_indexed_documents", title: "No documents were ready to search." },
    { reason: "weak_evidence", title: "No passage matched the question closely enough." },
    { reason: "insufficient_evidence", title: "The closest passages don't contain the answer." },
    { reason: "uncited_answer", title: "The model's reply didn't cite its sources." },
  ])("explains a question that wasn't answered because of $reason", async ({ reason, title }) => {
    const modelAsked = reason === "insufficient_evidence" || reason === "uncited_answer";
    installFetch({
      [HISTORY]: listOf(
        questionJson(
          {},
          {
            mode: modelAsked ? "generated" : "search_only",
            text: null,
            abstained: true,
            abstention_reason: reason,
            model_name: modelAsked ? MODEL_NAME : null,
            citations: [],
          },
        ),
      ),
    });
    renderPanel();

    const item = await findQuestionItem(QUESTION);

    expect(within(item).getByText(title)).toHaveClass("answer-declined-title");
    expect(within(item).getByText("Not answered")).toBeInTheDocument();
    expect(within(item).queryByRole("heading")).not.toBeInTheDocument();
    expect(within(item).queryByText(/^Written by/)).not.toBeInTheDocument();
  });

  it("explains that there are no recent questions", async () => {
    installFetch({ [HISTORY]: listOf() });
    renderPanel();

    expect(await screen.findByText(NO_QUESTIONS)).toBeInTheDocument();
  });

  it("offers a retry when recent questions can't load", async () => {
    const { routes } = installFetch({
      [HISTORY]: apiErrorResponse(503, "database_unavailable", "The database isn't available."),
    });
    renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent("The database isn't available.");
    routes[HISTORY] = listOf(questionJson());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await findQuestionItem(QUESTION)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports an ended session while loading recent questions", async () => {
    installFetch({ [HISTORY]: unauthenticatedResponse() });
    const { onSessionExpired } = renderPanel();

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });

  it("asks a question and lists its answer first", async () => {
    const reply = deferred();
    const { calls } = installFetch({
      [HISTORY]: listOf(questionJson({ id: "q-0", text: OLDER })),
      [ASK]: () => reply.promise,
    });
    renderPanel();
    await findQuestionItem(OLDER);

    typeQuestion(`  ${QUESTION}  `);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByRole("button", { name: "Asking…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByText(/^Searching the documents/)).toBeInTheDocument();
    expect(screen.getByText("Finding an answer…")).toBeInTheDocument();
    await waitFor(() => expect(callsTo(calls, ASK)).toHaveLength(1));
    expect(jsonBody(callsTo(calls, ASK)[0])).toEqual({ text: QUESTION });

    reply.resolve(jsonResponse(questionJson(), 201));

    expect(await screen.findByText("Answered, citing 1 source.")).toBeInTheDocument();
    expect(questionBox()).toHaveValue("");
    expect(listedQuestions()).toEqual([QUESTION, OLDER]);
    expect(questionItem(QUESTION)).toHaveAttribute("open");
    expect(questionItem(OLDER)).not.toHaveAttribute("open");
    expect(screen.queryByText(/^Searching the documents/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toHaveAttribute("aria-disabled", "true");
  });

  it.each([
    {
      outcome: "passages only",
      answer: { mode: "search_only", text: null, model_name: null },
      message: "No answer was written. Found 2 passages that match the question.",
    },
    {
      outcome: "no answer",
      answer: {
        mode: "search_only",
        text: null,
        abstained: true,
        abstention_reason: "weak_evidence",
        model_name: null,
        citations: [],
      },
      message: "Not answered. No passage matched the question closely enough.",
    },
  ])("announces an answer with $outcome", async ({ answer, message }) => {
    installFetch({
      [HISTORY]: listOf(),
      [ASK]: jsonResponse(
        questionJson({}, { citations: [citationJson(), SECOND_PASSAGE], ...answer }),
        201,
      ),
    });
    renderPanel();
    await screen.findByText(NO_QUESTIONS);

    typeQuestion(QUESTION);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("asks on Enter and leaves Shift+Enter for a new line", async () => {
    const { calls } = installFetch({
      [HISTORY]: listOf(),
      [ASK]: jsonResponse(questionJson(), 201),
    });
    renderPanel();
    await screen.findByText(NO_QUESTIONS);
    typeQuestion(QUESTION);

    expect(fireEvent.keyDown(questionBox(), { key: "Enter", shiftKey: true })).toBe(true);
    expect(fireEvent.keyDown(questionBox(), { key: "Enter", isComposing: true })).toBe(true);
    expect(callsTo(calls, ASK)).toHaveLength(0);

    expect(fireEvent.keyDown(questionBox(), { key: "Enter" })).toBe(false);

    expect(await screen.findByText("Answered, citing 1 source.")).toBeInTheDocument();
    expect(callsTo(calls, ASK)).toHaveLength(1);
  });

  it("keeps Ask unavailable until there's a question", async () => {
    const { calls } = installFetch({ [HISTORY]: listOf() });
    renderPanel();
    await screen.findByText(NO_QUESTIONS);

    typeQuestion("   ");
    const ask = screen.getByRole("button", { name: "Ask" });
    expect(ask).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(ask);
    expect(callsTo(calls, ASK)).toHaveLength(0);

    typeQuestion(QUESTION);
    expect(ask).not.toHaveAttribute("aria-disabled");
    expect(questionBox()).toHaveAccessibleDescription(
      "Press Enter to ask, or Shift+Enter for a new line.",
    );
  });

  it("waits for a Ready document before asking", async () => {
    const { calls } = installFetch({ [HISTORY]: listOf() });
    renderPanel({ readyCount: 0 });
    await screen.findByText(NO_QUESTIONS);

    typeQuestion(QUESTION);
    const ask = screen.getByRole("button", { name: "Ask" });
    fireEvent.click(ask);
    fireEvent.keyDown(questionBox(), { key: "Enter" });

    expect(ask).toHaveAttribute("aria-disabled", "true");
    expect(questionBox()).toHaveAccessibleDescription("You can ask once a document is Ready.");
    expect(callsTo(calls, ASK)).toHaveLength(0);
  });

  it("keeps the question and explains when it can't be answered", async () => {
    installFetch({
      [HISTORY]: listOf(),
      [ASK]: apiErrorResponse(
        503,
        "embedding_unavailable",
        "The search model isn't available. Try again shortly.",
      ),
    });
    renderPanel();
    await screen.findByText(NO_QUESTIONS);

    typeQuestion(QUESTION);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The search model isn't available. Try again shortly.",
    );
    expect(questionBox()).toHaveValue(QUESTION);
    expect(screen.getByRole("button", { name: "Ask" })).not.toHaveAttribute("aria-disabled");
    expect(screen.queryByText("Finding an answer…")).not.toBeInTheDocument();
  });

  it("reports an ended session while asking", async () => {
    installFetch({ [HISTORY]: listOf(), [ASK]: unauthenticatedResponse() });
    const { onSessionExpired } = renderPanel();
    await screen.findByText(NO_QUESTIONS);

    typeQuestion(QUESTION);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps what's typed while an answer is on its way", async () => {
    const reply = deferred();
    const { calls } = installFetch({ [HISTORY]: listOf(), [ASK]: () => reply.promise });
    renderPanel();
    await screen.findByText(NO_QUESTIONS);

    typeQuestion(QUESTION);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByRole("button", { name: "Asking…" });
    typeQuestion("Is parking free?");
    fireEvent.keyDown(questionBox(), { key: "Enter" });
    reply.resolve(jsonResponse(questionJson(), 201));

    expect(await screen.findByText("Answered, citing 1 source.")).toBeInTheDocument();
    expect(questionBox()).toHaveValue("Is parking free?");
    expect(callsTo(calls, ASK)).toHaveLength(1);
  });

  it.each([
    { list: "lacks it", items: [questionJson({ id: "q-0", text: OLDER })] },
    { list: "has it", items: [questionJson(), questionJson({ id: "q-0", text: OLDER })] },
  ])(
    "lists an answer once when it arrives before a list that $list",
    async ({ items }) => {
      const history = deferred();
      installFetch({
        [HISTORY]: () => history.promise,
        [ASK]: jsonResponse(questionJson(), 201),
      });
      renderPanel();

      typeQuestion(QUESTION);
      fireEvent.click(screen.getByRole("button", { name: "Ask" }));
      expect(await screen.findByText("Answered, citing 1 source.")).toBeInTheDocument();
      history.resolve(listOf(...items));

      await findQuestionItem(OLDER);
      expect(listedQuestions()).toEqual([QUESTION, OLDER]);
    },
  );

  it("loads recent questions again after asking if they couldn't load", async () => {
    const { routes } = installFetch({
      [HISTORY]: apiErrorResponse(503, "database_unavailable", "The database isn't available."),
      [ASK]: jsonResponse(questionJson(), 201),
    });
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent("The database isn't available.");

    routes[HISTORY] = listOf(questionJson(), questionJson({ id: "q-0", text: OLDER }));
    typeQuestion(QUESTION);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await findQuestionItem(OLDER);
    expect(listedQuestions()).toEqual([QUESTION, OLDER]);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("abandons a question still being answered when the panel closes", async () => {
    const reply = deferred();
    const { calls } = installFetch({ [HISTORY]: listOf(), [ASK]: () => reply.promise });
    const { unmount } = renderPanel();
    await screen.findByText(NO_QUESTIONS);

    typeQuestion(QUESTION);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(callsTo(calls, ASK)).toHaveLength(1));
    unmount();

    expect(callsTo(calls, ASK)[0]?.init.signal?.aborted).toBe(true);
  });

  it("downloads a cited document under its original name", async () => {
    installFetch({
      [HISTORY]: listOf(questionJson()),
      [DOWNLOAD]: new Response("%PDF-1.7 test", {
        headers: { "Content-Type": "application/pdf" },
      }),
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "Download guide.pdf" }));

    await waitFor(() => expect(saveBlob).toHaveBeenCalledTimes(1));
    const [blob, name] = vi.mocked(saveBlob).mock.calls[0] ?? [];
    expect(name).toBe("guide.pdf");
    await expect(readBlobText(blob ?? new Blob())).resolves.toBe("%PDF-1.7 test");
    expect(screen.getByRole("button", { name: "Download guide.pdf" })).toBeEnabled();
  });

  it("explains when a cited document can't be downloaded", async () => {
    installFetch({
      [HISTORY]: listOf(questionJson()),
      [DOWNLOAD]: apiErrorResponse(404, "document_not_found", "This document doesn't exist."),
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "Download guide.pdf" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This document doesn't exist.");
    expect(saveBlob).not.toHaveBeenCalled();
  });

  it("reports an ended session while downloading a cited document", async () => {
    installFetch({ [HISTORY]: listOf(questionJson()), [DOWNLOAD]: unauthenticatedResponse() });
    const { onSessionExpired } = renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "Download guide.pdf" }));

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("hides questions that cite a deleted document", async () => {
    installFetch({
      [HISTORY]: listOf(
        questionJson(),
        questionJson(
          { id: "q-2", text: OLDER },
          {
            citations: [
              citationJson({ document_id: "doc-2", document_name: "policy.txt", page_number: null }),
            ],
          },
        ),
      ),
    });
    const { rerender } = renderPanel();
    await findQuestionItem(OLDER);

    rerender({ deletedDocumentIds: new Set(["doc-1"]) });
    expect(listedQuestions()).toEqual([OLDER]);

    rerender({ deletedDocumentIds: new Set(["doc-1", "doc-2"]) });
    expect(listedQuestions()).toEqual([]);
    expect(screen.getByText(NO_QUESTIONS)).toBeInTheDocument();
  });

  it("lists five questions at first and the rest on request", async () => {
    const texts = Array.from({ length: 7 }, (_, index) => `Question ${index + 1}?`);
    installFetch({
      [HISTORY]: listOf(...texts.map((text, index) => questionJson({ id: `q-${index}`, text }))),
    });
    renderPanel();
    await findQuestionItem("Question 1?");

    expect(listedQuestions()).toEqual(texts.slice(0, 5));
    fireEvent.click(screen.getByRole("button", { name: "Show all 7" }));

    expect(listedQuestions()).toEqual(texts);
    expect(screen.queryByRole("button", { name: "Show all 7" })).not.toBeInTheDocument();
    expect(questionItem("Question 6?").querySelector("summary")).toHaveFocus();
  });

  it("counts the characters left near the limit", async () => {
    installFetch({ [HISTORY]: listOf() });
    renderPanel();
    await screen.findByText(NO_QUESTIONS);

    typeQuestion("a".repeat(899));
    expect(screen.queryByText(/left$/)).not.toBeInTheDocument();

    typeQuestion("a".repeat(900));
    expect(questionBox()).toHaveAccessibleDescription(
      "Press Enter to ask, or Shift+Enter for a new line. 100 characters left",
    );

    typeQuestion("a".repeat(999));
    expect(screen.getByText("1 character left")).toBeInTheDocument();
  });
});
