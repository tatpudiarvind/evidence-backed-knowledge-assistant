import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

function fillCredentials() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: USER.email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: PASSWORD } });
}

describe("AuthCard", () => {
  it("explains rejected credentials and lets the user try again", async () => {
    installFetch({
      "GET /health/ready": READY_RESPONSE,
      "POST /api/v1/auth/login": apiErrorResponse(
        401,
        "invalid_credentials",
        "The email or password is incorrect.",
        { requestId: "req-7" },
      ),
    });
    const onSignedIn = vi.fn();

    render(<AuthCard notice={null} onSignedIn={onSignedIn} />);
    fillCredentials();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The email or password is incorrect.");
    expect(alert).toHaveTextContent("Reference req-7");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("creates an account, which also signs it in", async () => {
    const { calls } = installFetch({
      "GET /health/ready": READY_RESPONSE,
      "POST /api/v1/auth/register": jsonResponse(USER, 201),
    });
    const onSignedIn = vi.fn();

    render(<AuthCard notice="You've signed out." onSignedIn={onSignedIn} />);
    expect(screen.getByText("You've signed out.")).toBeInTheDocument();
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
    expect(screen.queryByText("You've signed out.")).not.toBeInTheDocument();
  });

  it("lists field problems from the API", async () => {
    installFetch({
      "GET /health/ready": READY_RESPONSE,
      "POST /api/v1/auth/register": apiErrorResponse(
        422,
        "validation_failed",
        "Some fields are missing or invalid.",
        { fields: [{ location: "body.email", message: "Enter a valid email address." }] },
      ),
    });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Create an account" }));
    fillCredentials();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Some fields are missing or invalid.");
    expect(alert).toHaveTextContent("Email: Enter a valid email address.");
  });

  it("clears the password and error when switching forms", async () => {
    installFetch({
      "GET /health/ready": READY_RESPONSE,
      "POST /api/v1/auth/login": apiErrorResponse(401, "invalid_credentials", "Nope."),
    });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);
    fillCredentials();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Create an account" }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.getByLabelText("Email")).toHaveValue(USER.email);
  });

  it("offers another readiness check when services are down", async () => {
    installFetch({
      "GET /health/ready": jsonResponse({ status: "unavailable", database: "unavailable" }, 503),
    });

    render(<AuthCard notice={null} onSignedIn={vi.fn()} />);

    expect(await screen.findByText("API or database is unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(screen.getByText("Checking local services")).toBeInTheDocument();
    expect(await screen.findByText("API or database is unavailable")).toBeInTheDocument();
  });
});
