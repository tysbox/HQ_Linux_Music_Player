import { defineConfig, devices } from "@playwright/test";

/**
 * HQ Linux Music Player — Playwright E2E テスト設定.
 *
 * 既存 DSP:8000 / DMP:8001 への影響を最小化するため、
 * テストは hq_api:8002 のみをブラウザ越しに確認する。
 *
 * Firefox を使用（システムに既存インストール済み）。
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.HQ_BASE_URL || "http://localhost:3002",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
  ],
});
