import { useEffect, useRef, useState } from "react";

import { getReadiness } from "../../api/health";

type Readiness = "checking" | "ready" | "unavailable";

const LABELS: Record<Readiness, string> = {
  checking: "Checking local services",
  ready: "API and database are ready",
  unavailable: "API or database is unavailable",
};

export default function ServiceStatus() {
  const [state, setState] = useState<Readiness>("checking");
  const [attempt, setAttempt] = useState(0);
  const statusRef = useRef<HTMLParagraphElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const focusStatusWhenReady = useRef(false);
  const checking = state === "checking";

  useEffect(() => {
    const controller = new AbortController();
    getReadiness(controller.signal)
      .then(() => {
        // "Check again" is about to disappear, so keyboard focus needs somewhere to go.
        const button = buttonRef.current;
        focusStatusWhenReady.current = button !== null && document.activeElement === button;
        setState("ready");
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setState("unavailable");
        }
      });
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => {
    if (state === "ready" && focusStatusWhenReady.current) {
      focusStatusWhenReady.current = false;
      statusRef.current?.focus();
    }
  }, [state]);

  function checkAgain() {
    if (checking) {
      return;
    }
    setState("checking");
    setAttempt((value) => value + 1);
  }

  return (
    <div className="service-status">
      <p
        ref={statusRef}
        className={`health-row health-${state}`}
        role="status"
        tabIndex={-1}
      >
        <span className="health-dot" aria-hidden="true" />
        {LABELS[state]}
      </p>
      {/* The button stays during a repeat check, so it keeps keyboard focus. A disabled
          button would lose it, which is why this uses aria-disabled instead. */}
      {(state === "unavailable" || (checking && attempt > 0)) && (
        <button
          ref={buttonRef}
          type="button"
          className="button-link"
          aria-disabled={checking ? "true" : undefined}
          onClick={checkAgain}
        >
          Check again
        </button>
      )}
    </div>
  );
}
