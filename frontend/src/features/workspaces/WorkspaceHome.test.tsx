import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  apiErrorResponse,
  callsTo,
  documentJson,
  installFetch,
  jsonBody,
  jsonResponse,
  unauthenticatedResponse,
  workspaceJson,
} from "../../test/api";
import WorkspaceHome from "./WorkspaceHome";

describe("WorkspaceHome", () => {
  it("creates the first workspace and moves to its library", async () => {
    const { calls } = installFetch({
      "GET /api/v1/workspaces": jsonResponse({ items: [] }),
      "POST /api/v1/workspaces": jsonResponse(
        workspaceJson({ id: "ws-new", name: "Research notes" }),
        201,
      ),
      "GET /api/v1/workspaces/ws-new/documents": jsonResponse({ items: [] }),
    });

    render(<WorkspaceHome onSessionExpired={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText("Workspace name"), {
      target: { value: "  Research notes " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create workspace" }));

    const heading = await screen.findByRole("heading", { level: 1, name: "Research notes" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(await screen.findByText("This workspace is empty")).toBeInTheDocument();
    expect(jsonBody(callsTo(calls, "POST /api/v1/workspaces")[0])).toEqual({
      name: "Research notes",
    });
  });

  it("shows the API's reason when a workspace can't be created", async () => {
    installFetch({
      "GET /api/v1/workspaces": jsonResponse({ items: [] }),
      "POST /api/v1/workspaces": apiErrorResponse(
        422,
        "validation_failed",
        "Some fields are missing or invalid.",
        {
          fields: [
            { location: "body.name", message: "Workspace names must be 1 to 100 characters long." },
          ],
        },
      ),
    });

    render(<WorkspaceHome onSessionExpired={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText("Workspace name"), { target: { value: " " } });
    fireEvent.click(screen.getByRole("button", { name: "Create workspace" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Name: Workspace names must be 1 to 100 characters long.",
    );
  });

  it("switches between workspaces", async () => {
    installFetch({
      "GET /api/v1/workspaces": jsonResponse({
        items: [workspaceJson(), workspaceJson({ id: "ws-2", name: "Policies" })],
      }),
      "GET /api/v1/workspaces/ws-1/documents": jsonResponse({ items: [documentJson()] }),
      "GET /api/v1/workspaces/ws-2/documents": jsonResponse({
        items: [
          documentJson({
            id: "doc-2",
            workspace_id: "ws-2",
            display_name: "leave-policy.txt",
            mime_type: "text/plain",
          }),
        ],
      }),
    });

    render(<WorkspaceHome onSessionExpired={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "Download guide.pdf" })).toBeInTheDocument();
    const rail = screen.getByRole("navigation", { name: "Workspaces" });
    expect(within(rail).getByRole("button", { name: "Product manuals" })).toHaveAttribute(
      "aria-current",
      "true",
    );

    fireEvent.click(within(rail).getByRole("button", { name: "Policies" }));

    expect(
      await screen.findByRole("button", { name: "Download leave-policy.txt" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download guide.pdf" })).not.toBeInTheDocument();
    expect(within(rail).getByRole("button", { name: "Policies" })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("adds a workspace from the rail and selects it", async () => {
    installFetch({
      "GET /api/v1/workspaces": jsonResponse({ items: [workspaceJson()] }),
      "GET /api/v1/workspaces/ws-1/documents": jsonResponse({ items: [] }),
      "POST /api/v1/workspaces": jsonResponse(workspaceJson({ id: "ws-2", name: "Policies" }), 201),
      "GET /api/v1/workspaces/ws-2/documents": jsonResponse({ items: [] }),
    });

    render(<WorkspaceHome onSessionExpired={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText("New workspace"), {
      target: { value: "Policies" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Policies" })).toBeInTheDocument();
    expect(screen.getByText("Created Policies.")).toBeInTheDocument();
    expect(screen.getByLabelText("New workspace")).toHaveValue("");
  });

  it("offers a retry when workspaces can't load", async () => {
    const { routes } = installFetch({
      "GET /api/v1/workspaces": apiErrorResponse(500, "internal_error", "Something failed."),
    });

    render(<WorkspaceHome onSessionExpired={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Something failed.");

    routes["GET /api/v1/workspaces"] = jsonResponse({ items: [] });
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(
      await screen.findByRole("heading", { name: "Create your first workspace" }),
    ).toBeInTheDocument();
  });

  it("reports an ended session", async () => {
    installFetch({ "GET /api/v1/workspaces": unauthenticatedResponse() });
    const onSessionExpired = vi.fn();

    render(<WorkspaceHome onSessionExpired={onSessionExpired} />);

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
  });
});
