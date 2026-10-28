import { useCallback, useEffect, useState } from "react";

import { type User, getCurrentUser, signOut } from "./api/auth";
import ErrorNotice from "./components/ErrorNotice";
import AuthCard from "./features/auth/AuthCard";
import WorkspaceHome from "./features/workspaces/WorkspaceHome";

type Session =
  | { state: "checking" }
  | { state: "signed-out"; notice: string | null }
  | { state: "signed-in"; user: User };

const SESSION_ENDED_NOTICE = "Your session has ended. Sign in again to continue.";
const SIGNED_OUT_NOTICE = "You've signed out.";

export default function App() {
  const [session, setSession] = useState<Session>({ state: "checking" });
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<unknown>(null);

  useEffect(() => {
    const controller = new AbortController();
    getCurrentUser(controller.signal)
      .then((user) =>
        setSession(user ? { state: "signed-in", user } : { state: "signed-out", notice: null }),
      )
      .catch(() => {
        // The sign-in card reports whether the API is reachable.
        if (!controller.signal.aborted) {
          setSession({ state: "signed-out", notice: null });
        }
      });
    return () => controller.abort();
  }, []);

  const handleSignedIn = useCallback((user: User) => {
    setSignOutError(null);
    setSession({ state: "signed-in", user });
  }, []);

  const handleSessionExpired = useCallback(() => {
    setSignOutError(null);
    setSession({ state: "signed-out", notice: SESSION_ENDED_NOTICE });
  }, []);

  async function handleSignOut() {
    setSigningOut(true);
    setSignOutError(null);
    try {
      await signOut();
      setSession({ state: "signed-out", notice: SIGNED_OUT_NOTICE });
    } catch (error) {
      setSignOutError(error);
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="page-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Evidence-backed home">
          <span className="brand-mark" aria-hidden="true">
            E
          </span>
          <span>Evidence-backed</span>
        </a>
        {session.state === "signed-in" ? (
          <div className="account">
            <span className="account-email" title={session.user.email}>
              <span className="visually-hidden">Signed in as </span>
              {session.user.email}
            </span>
            <button
              type="button"
              className="button button-quiet button-small"
              onClick={handleSignOut}
              disabled={signingOut}
            >
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        ) : (
          <span className="topbar-note">A local-first knowledge workspace</span>
        )}
      </header>

      {session.state === "signed-in" && signOutError !== null && (
        <div className="page-alert">
          <ErrorNotice error={signOutError} />
        </div>
      )}

      {session.state === "checking" && (
        <main className="session-check">
          <p className="delayed-status" role="status">
            Checking your session…
          </p>
        </main>
      )}

      {session.state === "signed-out" && (
        <main className="hero" aria-labelledby="hero-title">
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
          <AuthCard notice={session.notice} onSignedIn={handleSignedIn} />
        </main>
      )}

      {session.state === "signed-in" && (
        <WorkspaceHome key={session.user.id} onSessionExpired={handleSessionExpired} />
      )}

      <footer className="page-footer">
        <span>Evidence before answers.</span>
        <span>Built to keep the source in view.</span>
      </footer>
    </div>
  );
}
