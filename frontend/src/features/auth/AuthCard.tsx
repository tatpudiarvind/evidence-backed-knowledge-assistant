import { type FormEvent, useId, useState } from "react";

import { type User, register, signIn } from "../../api/auth";
import ErrorNotice from "../../components/ErrorNotice";
import ServiceStatus from "./ServiceStatus";

type Mode = "sign-in" | "register";

type AuthCardProps = {
  /** A message from the app, such as why the user was signed out. */
  notice: string | null;
  onSignedIn: (user: User) => void;
};

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
  const id = useId();
  const copy = COPY[mode];
  const isRegister = mode === "register";

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
    setPassword("");
  }

  return (
    <section className="auth-card" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{copy.title}</h2>
      <p className="card-description">{copy.description}</p>
      {notice && showNotice && (
        <p className="auth-notice" role="status">
          {notice}
        </p>
      )}

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
          {pending ? copy.pending : copy.submit}
        </button>
      </form>

      <p className="auth-switch">
        {copy.switchPrompt}{" "}
        <button type="button" className="button-link" onClick={switchMode} disabled={pending}>
          {copy.switchAction}
        </button>
      </p>

      <ServiceStatus />
    </section>
  );
}
