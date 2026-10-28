import { describe, expect, it } from "vitest";

import { fileTypeLabel, formatDateTime, formatFileSize } from "./format";

// The app formats for the reader's locale, so expectations use the same formatter.
const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

describe("formatFileSize", () => {
  it("counts bytes below 1 KiB", () => {
    expect(formatFileSize(0)).toBe(`${number.format(0)} bytes`);
    expect(formatFileSize(1)).toBe("1 byte");
    expect(formatFileSize(1023)).toBe(`${number.format(1023)} bytes`);
  });

  it("uses binary units above that", () => {
    expect(formatFileSize(1024)).toBe(`${number.format(1)} KiB`);
    expect(formatFileSize(1536)).toBe(`${number.format(1.5)} KiB`);
    expect(formatFileSize(10 * 1024 * 1024)).toBe(`${number.format(10)} MiB`);
    expect(formatFileSize(2.25 * 1024 * 1024)).toBe(`${number.format(2.25)} MiB`);
  });
});

describe("formatDateTime", () => {
  it("formats timestamps for the reader's locale", () => {
    const value = "2025-01-03T09:30:00Z";
    const expected = new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));

    expect(formatDateTime(value)).toBe(expected);
  });

  it("leaves unreadable values as they are", () => {
    expect(formatDateTime("not a date")).toBe("not a date");
  });
});

describe("fileTypeLabel", () => {
  it("names the accepted file types", () => {
    expect(fileTypeLabel("application/pdf", "guide.pdf")).toBe("PDF");
    expect(fileTypeLabel(DOCX, "guide.docx")).toBe("DOCX");
    expect(fileTypeLabel("text/plain", "notes.txt")).toBe("TXT");
  });

  it("falls back to a short extension, then a generic label", () => {
    expect(fileTypeLabel("application/octet-stream", "archive.tar.gz")).toBe("GZ");
    expect(fileTypeLabel("application/octet-stream", "notes.markdown")).toBe("MARK");
    expect(fileTypeLabel("application/octet-stream", ".env")).toBe("FILE");
    expect(fileTypeLabel("application/octet-stream", "README")).toBe("FILE");
  });
});
