import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The version shown in the app ("About", sidebar) comes from package.json.
const { version } = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf8"),
) as {
  version: string;
};

export default defineConfig({
  define: { "import.meta.env.VITE_APP_VERSION": JSON.stringify(version) },
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      // 100 % for logic: pure functions, hooks, formatters and validation.
      include: [
        "src/lib/**/*.{ts,tsx}",
        "src/**/hooks/**/*.{ts,tsx}",
        "src/**/use-*.{ts,tsx}",
        // Form models, search parameters and error mapping are logic, too.
        "src/features/**/*-model.ts",
        "src/features/**/*-search.ts",
        "src/features/shared/server-errors.ts",
        "src/features/shared/form-schema.ts",
        // Pure helpers of the editor and the document pages.
        "src/features/documents/document-texts.ts",
        "src/features/documents/paid-rows.ts",
        "src/features/documents/file-download.ts",
        "src/features/documents/print-page.ts",
      ],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**"],
      thresholds: { lines: 100, branches: 100, functions: 100, statements: 100 },
    },
  },
});
