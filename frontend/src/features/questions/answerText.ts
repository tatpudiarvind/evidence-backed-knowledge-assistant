export type AnswerPart<T> =
  | { kind: "text"; text: string }
  | { kind: "citation"; number: number; citation: T };

const MARKER = /\[(\d+)\]/g;

/**
 * Splits a generated answer into its text and its [n] citation markers. Only numbers in
 * `citations` become citations; any other bracketed number stays part of the text.
 */
export function splitAnswer<T>(text: string, citations: ReadonlyMap<number, T>): AnswerPart<T>[] {
  const parts: AnswerPart<T>[] = [];
  let start = 0;
  for (const match of text.matchAll(MARKER)) {
    const number = Number(match[1]);
    const citation = citations.get(number);
    if (citation === undefined) {
      continue;
    }
    if (match.index > start) {
      parts.push({ kind: "text", text: text.slice(start, match.index) });
    }
    parts.push({ kind: "citation", number, citation });
    start = match.index + match[0].length;
  }
  if (start < text.length) {
    parts.push({ kind: "text", text: text.slice(start) });
  }
  return parts;
}
