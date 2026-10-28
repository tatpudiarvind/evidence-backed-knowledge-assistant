const KIB = 1024;
const MIB = KIB * 1024;

const TYPE_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
  "text/plain": "TXT",
};

const sizeFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** Sizes in binary units, matching the API's upload limit messages. */
export function formatFileSize(bytes: number): string {
  if (bytes < KIB) {
    return bytes === 1 ? "1 byte" : `${sizeFormat.format(bytes)} bytes`;
  }
  if (bytes < MIB) {
    return `${sizeFormat.format(bytes / KIB)} KiB`;
  }
  return `${sizeFormat.format(bytes / MIB)} MiB`;
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateFormat.format(date);
}

export function fileTypeLabel(mimeType: string, fileName: string): string {
  const known = TYPE_LABELS[mimeType];
  if (known) {
    return known;
  }
  const dot = fileName.lastIndexOf(".");
  const extension = dot > 0 ? fileName.slice(dot + 1, dot + 5) : "";
  return extension ? extension.toUpperCase() : "FILE";
}
