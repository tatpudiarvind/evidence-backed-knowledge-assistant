import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";
import { NETWORK_ERROR_MESSAGE } from "./api/client";
import {
  READY_RESPONSE,
  USER,
  callsTo,
  emptyResponse,
  installFetch,
  jsonBody,
  jsonResponse,
  unauthenticatedResponse,
  workspaceJson,
} from "./test/api";

const PASSWORD = "correct horse battery";

describe("App", () => {
  it("shows the sign-in card and service readiness to signed-out visitors", async () => {
    installFetch({
      "GET /api/v1/auth/me": unauthenticatedResponse(),
      "GET /health/ready": READY_RESPONSE,
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Good answers show their work." }),
    ).toBeInTheDocument();
    expect(await screen.findByText("API and database are ready")).toBeInTheDocument();
  });

  it("signs in and opens the first workspace", async () => {
    const { calls } = installFetch({
      "GET /api/v1/auth/me": unauthenticatedResponse(),
      "GET /health/ready": READY_RESPONSE,
      "POST /api/v1/auth/login": jsonResponse(USER),
      "GET /api/v1/workspaces": jsonResponse({ items: [workspaceJson()] }),
      "GET /api/v1/workspaces/ws-1/documents": jsonResponse({ items: [] }),
    });

    render(<App />);
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: USER.email } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: PASSWORD } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Product manuals" }),
    ).toBeInTheDocument();
    expect(screen.getByText(USER.email)).toBeInTheDocument();
    expect(jsonBody(callsTo(calls, "POST /api/v1/auth/login")[0])).toEqual({
      email: USER.email,
      password: PASSWORD,
    });
  });

  it("returns to sign-in when the session has ended", async () => {
    installFetch({
      "GET /api/v1/auth/me": jsonResponse(USER),
      "GET /health/ready": READY_RESPONSE,
      "GET /api/v1/workspaces": unauthenticatedResponse(),
    });

    render(<App />);

    expect(
      await screen.findByText("Your session has ended. Sign in again to continue."),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("signs out", async () => {
    installFetch({
      "GET /api/v1/auth/me": jsonResponse(USER),
      "GET /health/ready": READY_RESPONSE,
      "GET /api/v1/workspaces": jsonResponse({ items: [] }),
      "POST /api/v1/auth/logout": emptyResponse(),
    });

    render(<App />);
    expect(
      await screen.findByRole("heading", { name: "Create your first workspace" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByText("You've signed out.")).toBeInTheDocument();
    expect(screen.queryByText(USER.email)).not.toBeInTheDocument();
  });

  it("stays signed in and explains when signing out fails", async () => {
    installFetch({
      "GET /api/v1/auth/me": jsonResponse(USER),
      "GET /api/v1/workspaces": jsonResponse({ items: [] }),
      "POST /api/v1/auth/logout": () => {
        throw new TypeError("Failed to fetch");
      },
    });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(NETWORK_ERROR_MESSAGE);
    expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled();
    expect(screen.getByText(USER.email)).toBeInTheDocument();
  });
});
