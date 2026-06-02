import { expect, test } from "@playwright/test";

import { startRelayMatrixServer, type RelayMatrixServerHandle } from "./relayMatrixServer";

let backend: RelayMatrixServerHandle | null = null;

test.beforeAll(async () => {
  const apiPort = Number(process.env.E2E_API_PORT ?? 18181);
  backend = await startRelayMatrixServer({ apiPort });
  backend.writeValidRelayEnv();
});

test.afterAll(async () => {
  if (backend) {
    await backend.stop();
    backend = null;
  }
});

test("dashboard renders pipeline, services, and host tooling against the real backend", async ({ page }) => {
  if (!backend) throw new Error("Backend server was not initialized");

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "StreamTerminal Relay Matrix" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Current pipeline" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Operator actions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Services" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Host tooling snapshot" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent events" })).toBeVisible();

  // Pipeline panel shows primary/backup/output URLs from the live config.
  const pipelineSection = page
    .getByRole("heading", { name: "Current pipeline" })
    .locator("../..");
  await expect(pipelineSection).toContainText("Primary");
  await expect(pipelineSection).toContainText("Backup");
  await expect(pipelineSection).toContainText("Output");

  // Host tooling snapshot lists at least the well-known tools.
  const hostToolsSection = page
    .getByRole("heading", { name: "Host tooling snapshot" })
    .locator("../..");
  await expect(hostToolsSection).toContainText("mediamtx");
  await expect(hostToolsSection).toContainText("systemctl");
  await expect(hostToolsSection).toContainText("sudo");

  // Service list shows both services.
  const servicesSection = page
    .getByRole("heading", { name: "Services" })
    .locator("xpath=ancestor::div[contains(@class,'rounded-2xl')][1]");
  await expect(servicesSection.getByText("mediamtx", { exact: true })).toBeVisible();
  await expect(servicesSection.getByText("stream-failover-relay", { exact: true })).toBeVisible();
});

test("dashboard operator actions hit the real backend (apply draft, daemon-reload dry-run)", async ({ page }) => {
  await page.goto("/");

  // Apply draft -> POST /api/config/apply should produce a revision banner.
  await page.getByRole("button", { name: "Apply draft" }).click();

  // The banner is the first emerald section that appears after the click.
  // Match the exact banner text instead of using hasText regex (which has been finicky
  // when the same DOM also contains other sections that incidentally include the digits).
  await expect(
    page.locator("section.border-emerald-900", { hasText: "Applied draft as revision" })
  ).toBeVisible({ timeout: 10_000 });

  // Daemon-reload dry-run -> POST /api/services/mediamtx/action with execute=false.
  await page.getByRole("button", { name: "Daemon reload (dry-run)" }).click();
  await expect(
    page.locator("section.border-emerald-900", { hasText: "mediamtx daemon-reload dry-run prepared" })
  ).toBeVisible();
});

test("dashboard logs panel populates from the real backend", async ({ page }) => {
  await page.goto("/");

  // Click "Logs" on the first service (mediamtx). The fake journalctl is not present
  // in the sandbox, so the backend returns `available=false` with a clear detail.
  const servicesSection = page.getByRole("heading", { name: "Services" }).locator("..");
  await servicesSection.getByRole("button", { name: "Logs" }).first().click();
  await expect(page.getByText("Latest logs")).toBeVisible();
});
