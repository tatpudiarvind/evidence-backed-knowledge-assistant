import { useEffect, useState } from "react";

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

  useEffect(() => {
    const controller = new AbortController();
    getReadiness(controller.signal)
      .then(() => setState("ready"))
      .catch(() => {
        if (!controller.signal.aborted) {
          setState("unavailable");
        }
      });
    return () => controller.abort();
  }, [attempt]);

  function checkAgain() {
    setState("checking");
    setAttempt((value) => value + 1);
  }

  return (
    <div className="service-status">
      <p className={`health-row health-${state}`} role="status">
        <span className="health-dot" aria-hidden="true" />
        {LABELS[state]}
      </p>
      {state === "unavailable" && (
        <button type="button" className="button-link" onClick={checkAgain}>
          Check again
        </button>
      )}
    </div>
  );
}
