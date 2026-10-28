import { useId } from "react";

import type { Workspace } from "../../api/workspaces";
import CreateWorkspaceForm from "./CreateWorkspaceForm";

type WorkspaceRailProps = {
  workspaces: Workspace[];
  selectedId: string;
  onSelect: (workspaceId: string) => void;
  onCreated: (workspace: Workspace) => void;
  onSessionExpired: () => void;
};

function initial(name: string): string {
  return Array.from(name.trim())[0]?.toUpperCase() ?? "?";
}

export default function WorkspaceRail({
  workspaces,
  selectedId,
  onSelect,
  onCreated,
  onSessionExpired,
}: WorkspaceRailProps) {
  const id = useId();

  return (
    <div className="workspace-rail">
      <nav aria-labelledby={`${id}-title`}>
        <h2 id={`${id}-title`} className="rail-title">
          Workspaces
        </h2>
        <ul className="workspace-list">
          {workspaces.map((workspace) => (
            <li key={workspace.id}>
              <button
                type="button"
                className="workspace-button"
                aria-current={workspace.id === selectedId ? "true" : undefined}
                title={workspace.name}
                onClick={() => onSelect(workspace.id)}
              >
                <span className="workspace-initial" aria-hidden="true">
                  {initial(workspace.name)}
                </span>
                <span className="workspace-name">{workspace.name}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <CreateWorkspaceForm
        variant="rail"
        onCreated={onCreated}
        onSessionExpired={onSessionExpired}
      />
    </div>
  );
}
