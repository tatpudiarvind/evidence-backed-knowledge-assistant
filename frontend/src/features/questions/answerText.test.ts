import { describe, expect, it } from "vitest";

import { splitAnswer } from "./answerText";

const CITED = new Map([
  [1, "guide.pdf"],
  [2, "policy.docx"],
]);

describe("splitAnswer", () => {
  it("separates the text from its citation markers, in order", () => {
    expect(splitAnswer("Leave is 25 days [1]. Up to 5 carry over [2][1].", CITED)).toEqual([
      { kind: "text", text: "Leave is 25 days " },
      { kind: "citation", number: 1, citation: "guide.pdf" },
      { kind: "text", text: ". Up to 5 carry over " },
      { kind: "citation", number: 2, citation: "policy.docx" },
      { kind: "citation", number: 1, citation: "guide.pdf" },
      { kind: "text", text: "." },
    ]);
  });

  it("leaves numbers without a citation as text", () => {
    expect(splitAnswer("See clause [7] and [1].", CITED)).toEqual([
      { kind: "text", text: "See clause [7] and " },
      { kind: "citation", number: 1, citation: "guide.pdf" },
      { kind: "text", text: "." },
    ]);
  });

  it("handles markers at the edges and keeps line breaks", () => {
    expect(splitAnswer("[2] First.\nSecond [1]", CITED)).toEqual([
      { kind: "citation", number: 2, citation: "policy.docx" },
      { kind: "text", text: " First.\nSecond " },
      { kind: "citation", number: 1, citation: "guide.pdf" },
    ]);
  });

  it("returns text without markers unchanged", () => {
    expect(splitAnswer("No markers here.", CITED)).toEqual([
      { kind: "text", text: "No markers here." },
    ]);
    expect(splitAnswer("", CITED)).toEqual([]);
  });
});
