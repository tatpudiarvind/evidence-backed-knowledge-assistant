import { type FormEvent, useEffect, useId, useState } from "react";

import {
  type AuthOptions,
  DEFAULT_AUTH_OPTIONS,
  type User,
  getAuthOptions,
  providerSignInUrl,
  register,
  signIn,
} from "../../api/auth";
import ErrorNotice from "../../components/ErrorNotice";
import ServiceStatus from "./ServiceStatus";

type Mode = "sign-in" | "register";

type AuthCardProps = {
  /** A message from the app, such as why the user was signed out. */
  notice: string | null;
  onSignedIn: (user: User) => void;
};

/** What the server's short sign-in failure codes mean, in plain words. */
const SIGN_IN_ERRORS: Record<string, string> = {
  provider_unavailable: "The sign-in service can't be reached right now. Try again in a moment.",
  sign_in_expired: "That sign-in took too long or was already used. Start again.",
  email_not_verified:
    "The sign-in service hasn't verified your email address, so we can't use it for an account.",
  email_in_use:
    "An account with that email address already exists, and it isn't linked to this sign-in.",
};
const SIGN_IN_ERROR_FALLBACK = "The sign-in didn't go through. Try again.";
const SIGN_IN_ERROR_PARAMETER = "sign_in_error";

/** Reads the failure code the server leaves in the address, and takes it out of the address. */
function takeSignInError(): string | null {
  const address = new URL(window.location.href);
  const code = address.searchParams.get(SIGN_IN_ERROR_PARAMETER);
  if (code === null) {
    return null;
  }
  address.searchParams.delete(SIGN_IN_ERROR_PARAMETER);
  window.history.replaceState(window.history.state, "", address.pathname + address.search + address.hash);
  return SIGN_IN_ERRORS[code] ?? SIGN_IN_ERROR_FALLBACK;
}

const COPY = {
  "sign-in": {
    title: "Sign in",
    description: "Sign in to reach your workspaces and documents.",
    submit: "Sign in",
    pending: "Signing in…",
    switchPrompt: "New here?",
    switchAction: "Create an account",
  },
  register: {
    title: "Create your account",
    description: "Create a local account for this app.",
    submit: "Create account",
    pending: "Creating account…",
    switchPrompt: "Already have an account?",
    switchAction: "Sign in",
  },
} as const;

const PASSWORD_MIN_LENGTH = 12;

export default function AuthCard({ notice, onSignedIn }: AuthCardProps) {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [showNotice, setShowNotice] = useState(true);
  const [options, setOptions] = useState<AuthOptions | null>(null);
  const [signInError] = useState(takeSignInError);
  const id = useId();

  useEffect(() => {
    const controller = new AbortController();
    getAuthOptions(controller.signal)
      .then(setOptions)
      // If the server can't say, the local form is the safe thing to show; the server still
      // refuses a sign-in method that's off.
      .catch(() => {
        if (!controller.signal.aborted) {
          setOptions(DEFAULT_AUTH_OPTIONS);
        }
      });
    return () => controller.abort();
  }, []);

  const isRegister = mode === "register" && options?.registration === true;
  const providerName = options?.providerName ?? null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    setError(null);
    setShowNotice(false);
    const credentials = { email: email.trim(), password };
    try {
      const user = isRegister ? await register(credentials) : await signIn(credentials);
      onSignedIn(user);
    } catch (caught) {
      setError(caught);
      setPending(false);
    }
  }

  function switchMode() {
    setMode(isRegister ? "sign-in" : "register");
    setError(null);
    setShowNotice(false);
    setPassword("");
  }

  if (options === null) {
    return (
      <section className="auth-card" aria-labelledby={`${id}-title`} aria-busy="true">
        <h2 id={`${id}-title`}>Sign in</h2>
        <p className="card-description">Checking how this server signs people in…</p>
        <ServiceStatus />
      </section>
    );
  }

  const shownCopy = isRegister ? COPY.register : COPY["sign-in"];

  return (
    <section className="auth-card" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{options.password ? shownCopy.title : "Sign in"}</h2>
      <p className="card-description">
        {options.password
          ? shownCopy.description
          : `Sign in with your ${providerName ?? "identity provider"} account to reach your workspaces and documents.`}
      </p>
      {notice && showNotice && (
        <p className="auth-notice" role="status">
          {notice}
        </p>
      )}
      {signInError !== null && (
        <p className="auth-notice" role="alert">
          {signInError}
        </p>
      )}

      {providerName !== null && (
        <a
          className="button button-primary button-block"
          href={providerSignInUrl(window.location.pathname + window.location.search)}
        >
          Sign in with {providerName}
        </a>
      )}
      {providerName !== null && options.password && (
        <p className="auth-divider">or use an email and password</p>
      )}

      {options.password && (
        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor={`${id}-email`}>Email</label>
            <input
              id={`${id}-email`}
              className="text-input"
              type="email"
              autoComplete="email"
              required
              maxLength={320}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`${id}-password`}>Password</label>
            <input
              id={`${id}-password`}
              className="text-input"
              type="password"
              autoComplete={isRegister ? "new-password" : "current-password"}
              required
              minLength={isRegister ? PASSWORD_MIN_LENGTH : undefined}
              maxLength={128}
              aria-describedby={isRegister ? `${id}-password-hint` : undefined}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {isRegister && (
              <p id={`${id}-password-hint`} className="field-hint">
                At least {PASSWORD_MIN_LENGTH} characters.
              </p>
            )}
          </div>
          {error !== null && <ErrorNotice error={error} />}
          <button type="submit" className="button button-primary button-block" disabled={pending}>
            {pending ? shownCopy.pending : shownCopy.submit}
          </button>
        </form>
      )}

      {options.password && options.registration && (
        <p className="auth-switch">
          {shownCopy.switchPrompt}{" "}
          <button type="button" className="button-link" onClick={switchMode} disabled={pending}>
            {shownCopy.switchAction}
          </button>
        </p>
      )}

      <ServiceStatus />
    </section>
  );
}
