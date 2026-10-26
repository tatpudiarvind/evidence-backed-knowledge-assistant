import { useEffect, useState } from "react";

import { getReadiness } from "./lib/api";

type ReadinessState = "checking" | "ready" | "unavailable";

export default function App() {
  const [state, setState] = useState<ReadinessState>("checking");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState("checking");

    getReadiness(controller.signal)
      .then(() => setState("ready"))
      .catch(() => {
        if (!controller.signal.aborted) {
          setState("unavailable");
        }
      });

    return () => controller.abort();
  }, [attempt]);

  const statusText = {
    checking: "Checking local services",
    ready: "API and database are ready",
    unavailable: "API or database is unavailable",
  }[state];

  return (
    <main className="page-shell">
      <nav className="topbar" aria-label="Main navigation">
        <a className="brand" href="/" aria-label="Evidence-backed home">
          <span className="brand-mark" aria-hidden="true">
            E
          </span>
          <span>Evidence-backed</span>
        </a>
        <span className="topbar-note">A local-first knowledge workspace</span>
      </nav>

      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow">KNOWLEDGE, WITH ITS SOURCES</p>
          <h1 id="hero-title">
            Good answers
            <br />
            <span>show their work.</span>
          </h1>
          <p className="hero-description">
            A private place to explore your documents and get answers grounded in the evidence —
            with clear citations, and an honest “not enough information” when the sources fall
            short.
          </p>
          <div className="hero-note">
            <span aria-hidden="true">✳</span>
            <p>Designed for your local workspace. Your documents stay yours.</p>
          </div>
        </div>

        <aside className="status-card" aria-labelledby="status-title">
          <div className="card-topline">
            <span className="card-kicker">YOUR WORKSPACE</span>
            <span className={`status-indicator status-${state}`} aria-hidden="true" />
          </div>
          <div className="status-icon" aria-hidden="true">
            <svg viewBox="0 0 48 48" fill="none">
              <path d="M11 8.5h17l9 9v22H11z" />
              <path d="M28 8.5v10h9M17 27h14M17 33h14" />
              <path d="m18 19 3 3 6-6" />
            </svg>
          </div>
          <h2 id="status-title">A clear foundation.</h2>
          <p className="status-description">
            Your local services are the first step toward an evidence-ready library.
          </p>
          <div className={`health-row health-${state}`} role="status" aria-live="polite">
            <span className="health-dot" aria-hidden="true" />
            <span>{statusText}</span>
          </div>
          {state === "unavailable" && (
            <button className="retry-button" onClick={() => setAttempt((value) => value + 1)}>
              Check again
            </button>
          )}
          <div className="card-footer">
            <span>LOCAL DEVELOPMENT</span>
            <span>PHASE 01 / FOUNDATION</span>
          </div>
        </aside>
      </section>

      <footer className="page-footer">
        <span>Evidence before answers.</span>
        <span>Built to keep the source in view.</span>
      </footer>
    </main>
  );
}
