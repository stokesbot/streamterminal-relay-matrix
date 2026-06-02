import { expect, test, type Page, type Route } from "@playwright/test";

type DeployApiFixtureOptions = {
  executeMode?: "preview" | "apply" | "bundle" | "rollback";
};

const profile = {
  id: "local-system",
  label: "Local Linux host",
  description: "Install and operate the relay stack on the same machine where the control plane runs.",
  run_on: "local" as const,
  target_host: "localhost",
  target_user: "current-user",
  path_roots: {
    config_dir: "/etc/streamterminal-relay-matrix",
    bin_dir: "/usr/local/bin",
    systemd_dir: "/etc/systemd/system",
  },
  notes: ["This workflow is local-only: no SSH, rsync, or remote VPS copy steps are generated."],
  secret_placeholders: ["Create streamterminal-relay.env locally and keep it out of git."],
  source: "builtin" as const,
  editable: false,
};

const preflightOk = {
  profile,
  generated_at: "2026-06-02T17:20:41.429098+00:00",
  latest_revision: {
    version: 6,
    status: "applied",
    created_at: "2026-06-02T15:54:42.933715+00:00",
    note: "Applied local deployment bundle on host via profile local-system.",
  },
  summary: {
    ok: true,
    pass_count: 9,
    warn_count: 0,
    fail_count: 0,
  },
  checks: [
    {
      name: "Non-interactive sudo",
      status: "pass" as const,
      detail: "The API can escalate locally without prompting.",
      command: "sudo -n true",
    },
    {
      name: "Live relay env readiness",
      status: "pass" as const,
      detail: "The live env file is ready for automatic service start.",
      command: "test -f /etc/streamterminal-relay-matrix/streamterminal-relay.env",
    },
  ],
  warnings: [],
};

const plan = {
  profile,
  staged_root: "data/runtime/deploy-staging/local-system",
  generated_at: "2026-06-02T17:20:41.429098+00:00",
  latest_revision: {
    version: 6,
    status: "applied",
    created_at: "2026-06-02T15:54:42.933715+00:00",
    note: "Applied local deployment bundle on host via profile local-system.",
  },
  files: [
    {
      name: "mediamtx.yml",
      source_path: "data/runtime/deploy-staging/local-system/mediamtx.yml",
      target_path: "/etc/streamterminal-relay-matrix/mediamtx.yml",
      bytes: 512,
      exists_in_stage: true,
      preview: "paths:\n  live/main:\n    source: publisher\n  live/backup:\n    source: publisher\n",
    },
  ],
  commands: [
    {
      phase: "prepare" as const,
      label: "Ensure config directory exists",
      run_on: "local" as const,
      command: "sudo install -d -m 755 /etc/streamterminal-relay-matrix",
    },
    {
      phase: "verify" as const,
      label: "Check relay service health",
      run_on: "local" as const,
      command: "systemctl show stream-failover-relay.service --property ActiveState,SubState",
    },
  ],
  secret_templates: [
    {
      name: "streamterminal-relay.env",
      example_path: "/etc/streamterminal-relay-matrix/streamterminal-relay.env.example",
      live_path: "/etc/streamterminal-relay-matrix/streamterminal-relay.env",
      example_content: "OUTPUT_URL=rtmp://example.invalid/live/output\n",
      masked_current_values: {
        OUTPUT_URL: "rtmp://***",
      },
      notes: ["Keep this env file outside git."],
    },
  ],
  warnings: [],
};

const audit = {
  profile,
  generated_at: "2026-06-02T17:20:41.429098+00:00",
  latest_revision: {
    version: 6,
    status: "applied",
    created_at: "2026-06-02T15:54:42.933715+00:00",
    note: "Applied local deployment bundle on host via profile local-system.",
  },
  compared_bundle: "data/runtime/deploy-bundles/20260602T155201747189Z-local-system",
  summary: {
    total_files: 1,
    changed_files: 0,
    unchanged_files: 1,
    new_files: 0,
  },
  files: [
    {
      name: "mediamtx.yml",
      target_path: "/etc/streamterminal-relay-matrix/mediamtx.yml",
      bytes: 512,
      sha256: "abc123",
      previous_sha256: "abc123",
      changed: false,
      status: "unchanged" as const,
    },
  ],
};

const executePreview = {
  ok: true,
  executed: false,
  mode: "preview" as const,
  profile,
  bundle_root: "data/runtime/deploy-bundles/preview-local-system",
  host_touched: false,
  files_created: ["mediamtx.yml", "streamterminal-relay.env.example"],
  steps: [
    {
      label: "Build preview bundle",
      status: "created" as const,
      detail: "Wrote a local preview bundle without touching host paths.",
    },
  ],
  warnings: [],
  next_actions: ["Review the generated file previews before running a true local apply."],
};

const executeApplyFailure = {
  ok: false,
  executed: true,
  mode: "apply" as const,
  profile,
  bundle_root: "data/runtime/deploy-bundles/apply-local-system",
  host_touched: true,
  files_created: ["mediamtx.yml", "streamterminal-relay.env"],
  steps: [
    {
      label: "Restart relay service",
      status: "failed" as const,
      detail: "stream-failover-relay.service entered a crash loop because the env file still contains placeholders.",
    },
  ],
  warnings: ["Review the live env file before retrying apply."],
  next_actions: ["Fix the live env file and re-run preflight before applying again."],
};

async function installDeployApiFixtures(page: Page, options: DeployApiFixtureOptions = {}) {
  const executeMode = options.executeMode ?? "preview";

  await page.route("http://localhost:8000/api/deploy/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (method === "GET" && url.pathname.endsWith("/profiles")) {
      await fulfillJson(route, [profile]);
      return;
    }

    if (method === "GET" && url.pathname.endsWith("/preflight")) {
      await fulfillJson(route, preflightOk);
      return;
    }

    if (method === "GET" && url.pathname.endsWith("/plan")) {
      await fulfillJson(route, plan);
      return;
    }

    if (method === "GET" && url.pathname.endsWith("/audit")) {
      await fulfillJson(route, audit);
      return;
    }

    if (method === "POST" && url.pathname.endsWith("/execute")) {
      await fulfillJson(route, executeMode === "apply" ? executeApplyFailure : executePreview);
      return;
    }

    await route.abort();
  });
}

async function fulfillJson(route: Route, payload: unknown) {
  await route.fulfill({
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

test("deploy page loads local-only workflow and can run preflight/preview with mocked API", async ({ page }) => {
  await installDeployApiFixtures(page, { executeMode: "preview" });

  await page.goto("/deploy");

  await expect(page.getByRole("heading", { name: "Install and operate on this Linux host" })).toBeVisible();
  await expect(page.getByText("Local Linux host · current-user@localhost")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run local preflight" })).toBeVisible();
  await expect(page.getByRole("button", { name: "True local apply" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Local rollback" })).toBeVisible();

  const preflightSection = page.getByRole("heading", { name: "Local preflight" }).locator("..").locator("..");
  await expect(page.getByRole("heading", { name: "Local preflight" })).toBeVisible();
  await expect(page.getByText("Live relay env readiness")).toBeVisible();
  await expect(preflightSection.getByText("Ready", { exact: true })).toBeVisible();
  await expect(preflightSection.getByText("yes", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Run local preflight" }).click();
  await expect(page.getByText("The live env file is ready for automatic service start.")).toBeVisible();

  await page.getByRole("button", { name: "Preview local apply" }).click();
  await expect(page.getByRole("heading", { name: "Preview generated" })).toBeVisible();
  await expect(page.getByText("Mode: preview")).toBeVisible();
  await expect(page.getByText("Host touched: no")).toBeVisible();
  await expect(page.getByText("Review the generated file previews before running a true local apply.")).toBeVisible();
});

test("deploy page shows failed apply state from mocked API", async ({ page }) => {
  await installDeployApiFixtures(page, { executeMode: "apply" });

  await page.goto("/deploy");

  await page.getByRole("button", { name: "True local apply" }).click();

  await expect(page.getByRole("heading", { name: "True local apply reported failures" })).toBeVisible();
  await expect(page.getByText("Mode: apply")).toBeVisible();
  await expect(page.getByText("stream-failover-relay.service entered a crash loop because the env file still contains placeholders.")).toBeVisible();
  await expect(page.getByText("Fix the live env file and re-run preflight before applying again.")).toBeVisible();
});
