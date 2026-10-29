import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { READY_RESPONSE, callsTo, installFetch, jsonResponse } from "../../test/api";
import ServiceStatus from "./ServiceStatus";

const UNAVAILABLE = { status: "unavailable", database: "unavailable" };

/** Answers the first readiness check with a 503 and holds later checks until released. */
function installSlowRecheck() {
  let release: (response: Response) => void = () => undefined;
  const held = new Promise<Response>((resolve) => {
    release = resolve;
  });
  let checks = 0;
  const { calls } = installFetch({
    "GET /health/ready": () => {
      checks += 1;
      return checks === 1 ? jsonResponse(UNAVAILABLE, 503) : held;
    },
  });
  return { calls, release: (response: Response) => release(response) };
}

async function focusAndClickCheckAgain() {
  await screen.findByText("API or database is unavailable");
  const button = screen.getByRole("button", { name: "Check again" });
  button.focus();
  fireEvent.click(button);
  return button;
}

describe("ServiceStatus", () => {
  it("keeps Check again focused but unavailable while it checks again", async () => {
    const { calls, release } = installSlowRecheck();
    render(<ServiceStatus />);

    const button = await focusAndClickCheckAgain();

    expect(screen.getByRole("status")).toHaveTextContent("Checking local services");
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveFocus();
    fireEvent.click(button);
    expect(callsTo(calls, "GET /health/ready")).toHaveLength(2);

    release(jsonResponse(UNAVAILABLE, 503));

    expect(await screen.findByText("API or database is unavailable")).toBeInTheDocument();
    expect(button).not.toHaveAttribute("aria-disabled");
    expect(button).toHaveFocus();
  });

  it("moves focus to the status when the services become ready", async () => {
    const { release } = installSlowRecheck();
    render(<ServiceStatus />);

    await focusAndClickCheckAgain();
    release(READY_RESPONSE);

    expect(await screen.findByText("API and database are ready")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check again" })).not.toBeInTheDocument();
    // Focus moves in an effect, which can run just after the text changes.
    await waitFor(() => expect(screen.getByRole("status")).toHaveFocus());
  });
});
