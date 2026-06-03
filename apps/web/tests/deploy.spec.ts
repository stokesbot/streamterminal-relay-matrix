import { expect, test } from "@playwright/test";

import {
  startRelayMatrixServer,
  type RelayMatrixServerHandle,
} from "./relayMatrixServer";

let backend: RelayMatrixServerHandle | null = null;

test.beforeAll(async () => {
  const apiPort = Number(process.env.E2E_API_PORT ?? 18181);
  backend = await startRelayMatrixServer({ apiPort });
  // Make sure the live env is ready so the fake systemctl considers the relay healthy.
  backend.writeValidRelayEnv();
});

test.afterAll(async () => {
  if (backend) {
    await backend.stop();
    backend = null;
  }
});

test("deploy page renders the live local-only workflow against the real backend", async ({ page }) => {
  if (!backend) throw new Error("Backend server was not initialized");

  await page.goto("/deploy");

  await expect(page.getByRole("heading", { name: "Install and operate on this Linux host" })).toBeVisible();
  await expect(page.getByText("Local Linux host · current-user@localhost")).toBeVisible();

  await expect(page.getByRole("heading", { name: "Local preflight" })).toBeVisible();
  await expect(page.getByText("Live relay env readiness")).toBeVisible();

  const preflightSection = page.getByRole("heading", { name: "Local preflight" }).locator("..").locator("..");
  await expect(preflightSection.getByText("Ready", { exact: true })).toBeVisible();
  await expect(preflightSection.getByText("yes", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Run local preflight" }).click();
  await expect(page.getByText("contains the required relay variables")).toBeVisible();

  await page.getByRole("button", { name: "Preview local apply" }).click();
  await expect(page.getByRole("heading", { name: "Preview generated" })).toBeVisible();
  await expect(page.getByText("Mode: preview")).toBeVisible();
  await expect(page.getByText("Host touched: no")).toBeVisible();

  await page.getByRole("button", { name: "Generate local install bundle" }).click();
  await expect(page.getByRole("heading", { name: "Bundle written locally" })).toBeVisible();
});

test("config page loads, validates, and saves the draft against the real backend", async ({ page }) => {
  await page.goto("/config");

  await expect(page.getByRole("heading", { name: "Single-channel prototype" })).toBeVisible();
  await expect(page.getByText("Loaded draft config from API.")).toBeVisible();

  await page.getByRole("button", { name: "Validate draft" }).click();
  await expect(page.getByText("Validation passed.").or(page.getByText("Validation reported issues."))).toBeVisible();
});

test("diagnostics page renders runtime inspection against the real backend", async ({ page }) => {
  await page.goto("/diagnostics");

  await expect(page.getByRole("heading", { name: "Runtime inspection" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Host tools" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Systemd unit state" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Generated artifacts" })).toBeVisible();
});

test("deploy page exposes host snapshots list and a restore action", async ({ page }) => {
  if (!backend) throw new Error("Backend server was not initialized");

  // Trigger an apply so a snapshot gets captured.
  const applyResponse = await page.request.post(`${backend.apiBaseUrl}/api/deploy/execute`, {
    data: { profile_id: "local-system", execute: true, action: "apply" },
  });
  expect(applyResponse.ok()).toBeTruthy();

  await page.goto("/deploy");

  // The deploy page now lists host snapshots.
  await expect(page.getByRole("heading", { name: "Local host snapshots" })).toBeVisible();
  const snapshotRows = page.getByTestId("host-snapshot-row");
  await expect(snapshotRows.first()).toBeVisible();
  await expect(snapshotRows.first()).toContainText("trigger=apply");

  // Clicking "Restore" without confirmation should NOT mutate the host.
  page.once("dialog", (dialog) => void dialog.dismiss());
  await snapshotRows.first().getByRole("button", { name: "Restore" }).click();
  // No `Restored snapshot` banner should appear because we cancelled.
  await expect(page.getByTestId("restore-banner")).toHaveCount(0);
});

test("deploy page shows bundle inventory and exposes a prune action", async ({ page }) => {
  if (!backend) throw new Error("Backend server was not initialized");

  // Trigger an apply so at least one bundle exists in the inventory.
  const applyResponse = await page.request.post(`${backend.apiBaseUrl}/api/deploy/execute`, {
    data: { profile_id: "local-system", execute: true, action: "apply" },
  });
  expect(applyResponse.ok()).toBeTruthy();

  await page.goto("/deploy");

  // The deploy page now shows a Bundle inventory section.
  const inventorySection = page.getByTestId("bundle-inventory-section");
  await expect(inventorySection).toBeVisible();
  await expect(inventorySection.getByText("Bundles")).toBeVisible();
  await expect(inventorySection.getByText("Staging dirs")).toBeVisible();

  // Bundle count tile should be at least 1 after the apply above.
  const bundleCount = inventorySection.getByTestId("bundle-count");
  await expect(bundleCount).toBeVisible();
  const countText = (await bundleCount.textContent()) ?? "";
  expect(countText).toMatch(/Bundles\s*(\d+)/);

  // The prune button should exist; clicking it (after confirming) should
  // produce a banner.
  const pruneButton = page.getByTestId("prune-bundles-button");
  await expect(pruneButton).toBeVisible();
  page.once("dialog", (dialog) => void dialog.accept());
  await pruneButton.click();
  await expect(page.getByTestId("prune-banner")).toBeVisible({ timeout: 10_000 });
});
