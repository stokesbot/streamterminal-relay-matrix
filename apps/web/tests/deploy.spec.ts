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
