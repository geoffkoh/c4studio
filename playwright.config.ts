import { defineConfig, devices } from "@playwright/test";

/**
 * Visual and layout coverage for the Studio.
 *
 * Five layout changes landed with ~60 assertions on their state machines
 * and none at all on the layout, because the environment they were written
 * in had no browser. These tests are the other half: they assert the things
 * `tsc` cannot see — that a pane has height, that chrome does not eat the
 * window, that a breakpoint fires where the arithmetic said it would.
 *
 * Playwright starts the real backend, so what is under test is the same
 * committed bundle a user gets, served the same way.
 */
const PORT = 8099;

export default defineConfig({
  testDir: "./e2e",
  // Layout is deterministic; a retry here would only hide a flake worth
  // knowing about.
  retries: 0,
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // Screenshots are compared across machines, so nothing may depend on
    // the host's fonts or device pixel ratio more than it must.
    deviceScaleFactor: 1,
    ...devices["Desktop Chrome"],
  },
  expect: {
    toHaveScreenshot: {
      // Anti-aliasing differs slightly between machines; a layout shift
      // does not. This threshold catches the latter and tolerates the
      // former.
      maxDiffPixelRatio: 0.02,
      animations: "disabled",
    },
  },
  webServer: {
    // The real CLI, the real FastAPI app, the committed bundle. Serving
    // `samples/` read-only: no test writes to disk.
    command: `uv run c4 webapp samples/ --port ${PORT} --host 127.0.0.1 --no-browser`,
    url: `http://127.0.0.1:${PORT}/api/capabilities`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
