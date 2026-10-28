import { type FormEvent, useId, useState } from "react";

import { isUnauthenticated } from "../../api/client";
import { type Workspace, createWorkspace } from "../../api/workspaces";
import ErrorNotice from "../../components/ErrorNotice";

type CreateWorkspaceFormProps = {
  /** "rail" sits under the workspace list; "onboarding" is the first-run form. */
  variant: "rail" | "onboarding";
  onCreated: (workspace: Workspace) => void;
  onSessionExpired: () => void;
};

export default function CreateWorkspaceForm({
  variant,
  onCreated,
  onSessionExpired,
}: CreateWorkspaceFormProps) {
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [createdName, setCreatedName] = useState<string | null>(null);
  const id = useId();
  const isRail = variant === "rail";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    setError(null);
    setCreatedName(null);
    try {
      const workspace = await createWorkspace(name.trim());
      setName("");
      setCreatedName(workspace.name);
      setPending(false);
      onCreated(workspace);
    } catch (caught) {
      setPending(false);
      if (isUnauthenticated(caught)) {
        onSessionExpired();
        return;
      }
      setError(caught);
    }
  }

  const submitLabel = isRail ? "Create" : "Create workspace";

  return (
    <form className={`create-workspace create-workspace-${variant}`} onSubmit={handleSubmit}>
      <label htmlFor={`${id}-name`}>{isRail ? "New workspace" : "Workspace name"}</label>
      <div className="inline-field">
        <input
          id={`${id}-name`}
          className="text-input"
          type="text"
          required
          maxLength={100}
          autoComplete="off"
          placeholder="e.g. Product manuals"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button
          type="submit"
          className={`button ${isRail ? "button-secondary" : "button-primary"}`}
          disabled={pending}
        >
          {pending ? "Creating…" : submitLabel}
        </button>
      </div>
      {error !== null && <ErrorNotice error={error} />}
      {isRail && (
        <p className="visually-hidden" role="status">
          {createdName ? `Created ${createdName}.` : ""}
        </p>
      )}
    </form>
  );
}
