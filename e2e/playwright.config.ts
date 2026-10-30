import { defineConfig, devices } from "@playwright/test";

// The tests drive a running copy of the app; they don't start one. CI runs them against the
// production-style stack (compose.prod.yaml), as docs/operations/README.md describes.
export default defineConfig({
  testDir: "./tests",
  // One browser at a time: the tests share the API's per-address rate limits.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  // Indexing the first document also loads the embedding model.
  timeout: 180_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  outputDir: "test-results",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } },
    },
  ],
});
