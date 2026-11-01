import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  READY_RESPONSE,
  USER,
  apiErrorResponse,
  callsTo,
  installFetch,
  jsonBody,
  jsonResponse,
} from "../../test/api";
import AuthCard from "./AuthCard";

const PASSWORD = "correct horse battery";
const LOCAL_ONLY = {
  "GET /api/v1/auth/options": jsonResponse({
    password: true,
    registration: true,
    provider_name: null,
  }),
};

/** The card shows its form once it knows how the server signs people in. */
async function formReady() {
  await screen.findByLabelText("Email");
}

function fillCredentials() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: USER.email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: PASSWORD } });
}

describe("AuthCard", () => {
  it("explains rejected credentials and lets the user try again", async () => {
    installFetch({
      ...LOCAL_ONLY,
      "GET /health/ready": READY_RESPONSE,
      "POST /api/v1/auth/login": apiErrorResponse(
        401,
        "invalid_credentials",
        "The email or password is incorrect.",
        { requestId: "req-7" },
      ),
    });
    const onSignedIn = vi.fn();

    render(<AuthCard notice="You've signed out." onSignedIn={onSignedIn} />);
    await formReady();
    expect(screen.getByText("You've signed out.")).toBeInTheDocument();
    fillCredentials();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The email or password is incorrect.");
    expect(alert).toHaveTextContent("Reference req-7");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
    expect(screen.queryByText("You've signed out.")).not.toBeInTheDocument();
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("creates an account, which also signs it in", async () => {
    const { calls } = installFetch({
      ...LOCAL_ONLY,
      "GET /health/ready": READY_RESPONSE,
      "POST /api/v1/auth/register": jsonResponse(USER, 201),
    });
    const onSignedIn = vi.fn();

    render(<AuthCard notice={null} onSignedIn={onSignedIn} />);
    await formReady();
    fireEvent.click(screen.getByRole("button", { name: "Create an account" }));

    expect(screen.getByRole("heading", { name: "Create your account" })).toBeInTheDocument();
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("autocomplete", "new-password");
    expect(password).toHaveAttribute("minlength", "12");
    expect(password).toHaveAccessibleDescription("At least 12 characters.");

    fillCredentials();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(onSignedIn).toHaveBeenCalledWith(USER));
    expect(jsonBody(callsTo(calls, "POST /api/v1/auth/register")[0])).toEqual({
      email: USER.email,
      password: PASSWORD,
    });
  });

  it("lists field problems from the API", async () => {
    installFetch({
      ...LOCAL_ONLY,
      "GET /health/ready": READY_RESPONSE,
      "POST /api/v1/auth/register": apiErrorResponse(
        422,
        "validation_failed",
        "Some fields are missing or invalid.",
        { fields: [{ location: "body.email", message: "Enter a valid email address." }] },
      ),
    });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);
    await formReady();
    fireEvent.click(screen.getByRole("button", { name: "Create an account" }));
    fillCredentials();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Some fields are missing or invalid.");
    expect(alert).toHaveTextContent("Email: Enter a valid email address.");
  });

  it("clears the password and error when switching forms", async () => {
    installFetch({
      ...LOCAL_ONLY,
      "GET /health/ready": READY_RESPONSE,
      "POST /api/v1/auth/login": apiErrorResponse(401, "invalid_credentials", "Nope."),
    });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);
    await formReady();
    fillCredentials();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Create an account" }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.getByLabelText("Email")).toHaveValue(USER.email);
  });

  it("hides the sign-out notice once the user switches forms", async () => {
    installFetch({ ...LOCAL_ONLY, "GET /health/ready": READY_RESPONSE });

    render(<AuthCard notice="You've signed out." onSignedIn={vi.fn()} />);
    await formReady();
    expect(screen.getByText("You've signed out.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create an account" }));

    expect(screen.queryByText("You've signed out.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.queryByText("You've signed out.")).not.toBeInTheDocument();
  });

  it("offers another readiness check when services are down", async () => {
    installFetch({
      ...LOCAL_ONLY,
      "GET /health/ready": jsonResponse({ status: "unavailable", database: "unavailable" }, 503),
    });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);

    expect(await screen.findByText("API or database is unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(screen.getByText("Checking local services")).toBeInTheDocument();
    expect(await screen.findByText("API or database is unavailable")).toBeInTheDocument();
  });
});

describe("AuthCard with an identity provider", () => {
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  function options(body: Record<string, unknown>) {
    installFetch({
      "GET /api/v1/auth/options": jsonResponse(body),
      "GET /health/ready": READY_RESPONSE,
    });
  }

  it("offers only the provider when passwords are off", async () => {
    options({ password: false, registration: false, provider_name: "Example ID" });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);

    const link = await screen.findByRole("link", { name: "Sign in with Example ID" });
    expect(link).toHaveAttribute("href", "/api/v1/auth/oidc/login?return_to=%2F");
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create an account" })).not.toBeInTheDocument();
  });

  it("offers both ways when both are on", async () => {
    options({ password: true, registration: true, provider_name: "Example ID" });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);

    expect(await screen.findByRole("link", { name: "Sign in with Example ID" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create an account" })).toBeInTheDocument();
  });

  it("hides account creation when registration is closed", async () => {
    options({ password: true, registration: false, provider_name: null });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);

    await screen.findByLabelText("Email");
    expect(screen.queryByRole("button", { name: "Create an account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("falls back to the password form when the options can't be read", async () => {
    installFetch({ "GET /health/ready": READY_RESPONSE });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);

    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create an account" })).toBeInTheDocument();
  });

  it("explains a failed sign-in and takes the code out of the address", async () => {
    window.history.replaceState(null, "", "/?sign_in_error=email_in_use&keep=1");
    options({ password: false, registration: false, provider_name: "Example ID" });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("already exists");
    expect(window.location.search).toBe("?keep=1");
  });

  it("gives a plain message for a code it doesn't know", async () => {
    window.history.replaceState(null, "", "/?sign_in_error=<script>");
    options({ password: false, registration: false, provider_name: "Example ID" });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("The sign-in didn't go through.");
    expect(window.location.search).toBe("");
  });
});