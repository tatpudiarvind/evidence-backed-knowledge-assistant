import { ApiError } from "../api/client";

const FALLBACK_MESSAGE = "Something went wrong. Try again.";

type ErrorNoticeProps = {
  error: unknown;
  /** Announce the error when it appears. Turn off for errors listed among other content. */
  live?: boolean;
};

function fieldLabel(location: string): string | null {
  const name = location
    .split(".")
    .filter((part) => part !== "body")
    .at(-1);
  if (!name) {
    return null;
  }
  const words = name.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export default function ErrorNotice({ error, live = true }: ErrorNoticeProps) {
  const apiError = error instanceof ApiError ? error : null;
  const fields = apiError?.fields ?? [];

  return (
    <div className="error-notice" role={live ? "alert" : undefined}>
      <p className="error-message">{apiError?.message ?? FALLBACK_MESSAGE}</p>
      {fields.length > 0 && (
        <ul className="error-fields">
          {fields.map((field, index) => {
            const label = fieldLabel(field.location);
            return (
              <li key={`${field.location}-${index}`}>
                {label ? `${label}: ${field.message}` : field.message}
              </li>
            );
          })}
        </ul>
      )}
      {apiError?.requestId && (
        <p className="error-reference">
          Reference <code>{apiError.requestId}</code>
        </p>
      )}
    </div>
  );
}
