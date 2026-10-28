import { useCallback, useEffect, useState } from "react";

import { isUnauthenticated } from "../../api/client";
import { type Workspace, listWorkspaces } from "../../api/workspaces";
import ErrorNotice from "../../components/ErrorNotice";
import DocumentLibrary from "../documents/DocumentLibrary";
import CreateWorkspaceForm from "./CreateWorkspaceForm";
import WorkspaceRail from "./WorkspaceRail";

type Load =
  | { state: "loading" }
  | { state: "error"; error: unknown }
  | { state: "loaded"; workspaces: Workspace[] };

type WorkspaceHomeProps = {
  onSessionExpired: () => void;
};

export default function WorkspaceHome({ onSessionExpired }: WorkspaceHomeProps) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Set when the first workspace is created, so focus can follow the page change.
  const [focusLibraryId, setFocusLibraryId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listWorkspaces(controller.signal)
      .then((workspaces) => setLoad({ state: "loaded", workspaces }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (isUnauthenticated(error)) {
          onSessionExpired();
          return;
        }
        setLoad({ state: "error", error });
      });
    return () => controller.abort();
  }, [attempt, onSessionExpired]);

  const handleCreated = useCallback((workspace: Workspace) => {
    setLoad((current) => ({
      state: "loaded",
      workspaces: current.state === "loaded" ? [...current.workspaces, workspace] : [workspace],
    }));
    setSelectedId(workspace.id);
  }, []);

  const handleFirstCreated = useCallback(
    (workspace: Workspace) => {
      handleCreated(workspace);
      setFocusLibraryId(workspace.id);
    },
    [handleCreated],
  );

  const handleSelect = useCallback((workspaceId: string) => {
    setSelectedId(workspaceId);
    setFocusLibraryId(null);
  }, []);

  function retry() {
    setLoad({ state: "loading" });
    setAttempt((value) => value + 1);
  }

  if (load.state === "loading") {
    return (
      <div className="app-layout" aria-busy="true">
        <div className="workspace-rail" aria-hidden="true">
          <span className="skeleton skeleton-label" />
          <span className="skeleton skeleton-item" />
          <span className="skeleton skeleton-item" />
        </div>
        <main className="library">
          <p className="visually-hidden" role="status">
            Loading your workspaces…
          </p>
          <div className="library-loading" aria-hidden="true">
            <span className="skeleton skeleton-heading" />
            <span className="skeleton skeleton-panel" />
          </div>
        </main>
      </div>
    );
  }

  if (load.state === "error") {
    return (
      <main className="state-panel">
        <h1>Your workspaces couldn't load</h1>
        <ErrorNotice error={load.error} />
        <button type="button" className="button button-secondary" onClick={retry}>
          Try again
        </button>
      </main>
    );
  }

  const { workspaces } = load;
  const selected = workspaces.find((workspace) => workspace.id === selectedId) ?? workspaces[0];

  if (!selected) {
    return (
      <main className="state-panel onboarding">
        <h1>Create your first workspace</h1>
        <p className="state-description">
          A workspace keeps related documents together. Questions you ask later are answered only
          from the documents in that workspace.
        </p>
        <CreateWorkspaceForm
          variant="onboarding"
          onCreated={handleFirstCreated}
          onSessionExpired={onSessionExpired}
        />
      </main>
    );
  }

  return (
    <div className="app-layout">
      <WorkspaceRail
        workspaces={workspaces}
        selectedId={selected.id}
        onSelect={handleSelect}
        onCreated={handleCreated}
        onSessionExpired={onSessionExpired}
      />
      <main className="library">
        <DocumentLibrary
          key={selected.id}
          workspace={selected}
          focusHeading={focusLibraryId === selected.id}
          onSessionExpired={onSessionExpired}
        />
      </main>
    </div>
  );
}
