import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import App from "./App";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok", database: "ok" }),
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the foundation and local service readiness", async () => {
    render(<App />);

    expect(
      await screen.findByText("API and database are ready"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Good answers show their work." }),
    ).toBeInTheDocument();
  });
});
