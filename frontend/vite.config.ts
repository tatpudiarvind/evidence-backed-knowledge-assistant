import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // One .env at the repository root configures both the API and the web app.
  // Vite exposes only VITE_* values to the browser.
  envDir: fileURLToPath(new URL("..", import.meta.url)),
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
