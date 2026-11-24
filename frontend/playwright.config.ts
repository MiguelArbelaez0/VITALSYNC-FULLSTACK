import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5188",
    ...(process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : {}),
    launchOptions: {
      args: process.env.E2E_LIVEKIT_PHYSICAL === "true"
        ? ["--use-fake-ui-for-media-stream"]
        : ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
    },
    trace: process.env.E2E_LIVEKIT_PHYSICAL === "true" ? "off" : "retain-on-failure",
    screenshot: process.env.E2E_LIVEKIT_PHYSICAL === "true" ? "off" : "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  reporter: [["list"], ["html", { open: "never" }]],
});
