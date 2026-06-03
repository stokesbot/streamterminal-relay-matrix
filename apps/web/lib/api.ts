const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export type RelayConfig = {
  channel_name: string;
  mediamtx_enabled: boolean;
  relay_enabled: boolean;
  auto_restart: boolean;
  primary_input: {
    label: string;
    protocol: string;
    url: string;
    mode: string;
    enabled: boolean;
  };
  backup_input: {
    label: string;
    protocol: string;
    url: string;
    mode: string;
    enabled: boolean;
  };
  output: {
    label: string;
    protocol: string;
    url: string;
    mode: string;
    enabled: boolean;
  };
};

export type RuntimeStatus = {
  active_source: string;
  primary_state: string;
  backup_state: string;
  output_state: string;
  primary_bytes: number;
  backup_bytes: number;
  output_bytes: number;
  services: Array<{ name: string; status: string; detail: string }>;
  recent_events: string[];
  probe_method: string;
  probe_success: boolean;
};

export type ValidationResult = {
  valid: boolean;
  issues: Array<{ level: "info" | "warning" | "error"; message: string }>;
};

export type ApplyResult = {
  ok: boolean;
  version: number;
  note: string;
  artifacts: string[];
};

export type InstallResult = {
  ok: boolean;
  installed_to: string;
  artifacts: string[];
};

export type ServiceAction =
  | "start"
  | "stop"
  | "restart"
  | "reload"
  | "status"
  | "daemon-reload";

export type ServiceName = "mediamtx" | "stream-failover-relay";
export type DeploymentProfileId = string;

export type ServiceActionResult = {
  ok: boolean;
  executed: boolean;
  service: ServiceName;
  unit: string;
  action: ServiceAction;
  command: string[];
  stdout: string;
  stderr: string;
  exit_code: number;
};

export type ServiceLogsResponse = {
  service: ServiceName;
  unit: string;
  available: boolean;
  detail: string;
  command?: string[];
  exit_code?: number;
  lines: string[];
};

export type GeneratedArtifact = {
  name: string;
  path: string;
  content: string;
};

export type DeploymentProfile = {
  id: DeploymentProfileId;
  label: string;
  description: string;
  run_on: "local";
  target_host: string;
  target_user: string;
  path_roots: Record<string, string>;
  notes: string[];
  secret_placeholders: string[];
  source: "builtin";
  editable: boolean;
};

export type DeploymentSecretTemplate = {
  name: string;
  example_path: string;
  live_path: string;
  example_content: string;
  masked_current_values: Record<string, string>;
  notes: string[];
};

export type DeploymentPreflight = {
  profile: DeploymentProfile;
  generated_at: string;
  latest_revision?: {
    version: number;
    status: string;
    created_at: string;
    note: string;
  } | null;
  summary: {
    ok: boolean;
    pass_count: number;
    warn_count: number;
    fail_count: number;
  };
  checks: Array<{
    name: string;
    status: "pass" | "warn" | "fail";
    detail: string;
    command?: string | null;
  }>;
  warnings: string[];
};

export type DeploymentPlan = {
  profile: DeploymentProfile;
  staged_root: string;
  generated_at: string;
  latest_revision?: {
    version: number;
    status: string;
    created_at: string;
    note: string;
  } | null;
  files: Array<{
    name: string;
    source_path: string;
    target_path: string;
    bytes: number;
    exists_in_stage: boolean;
    preview: string;
  }>;
  commands: Array<{
    phase: "prepare" | "copy" | "activate" | "verify";
    label: string;
    run_on: "local";
    command: string;
  }>;
  secret_templates: DeploymentSecretTemplate[];
  warnings: string[];
};

export type SmokeCheckStatus = "pass" | "warn" | "fail";

export type SmokeCheck = {
  name: string;
  status: SmokeCheckStatus;
  detail: string;
};

export type SmokeSummary = {
  ok: boolean;
  pass_count: number;
  warn_count: number;
  fail_count: number;
};

export type SmokeResponse = {
  generated_at: string;
  ok: boolean;
  summary: SmokeSummary;
  checks: SmokeCheck[];
};

export type HostSnapshotSummary = {
  id: string;
  created_at: string;
  trigger: string;
  host_root: string;
  manifest_path: string;
  file_count: number;
  total_bytes: number;
  note: string | null;
};

export type HostSnapshotListResponse = {
  generated_at: string;
  snapshots: HostSnapshotSummary[];
};

export type HostSnapshotRestoreResult = {
  ok: boolean;
  executed: boolean;
  snapshot_id: string;
  host_root: string;
  restored?: Array<{
    path: string;
    command: string;
    ok: boolean;
    exit_code: number;
  }>;
  files?: Array<{
    path: string;
    size: number;
    sha256: string;
  }>;
};

export type BundleInventoryItem = {
  name: string;
  path: string;
  size_bytes: number;
  file_count: number;
  modified_at: string;
  mtime: number;
  host_touched: boolean;
  mode: string | null;
};

export type BundleInventoryResponse = {
  generated_at: string;
  bundle_root: string;
  install_root: string;
  bundle_count: number;
  bundle_total_bytes: number;
  staging_count: number;
  staging_total_bytes: number;
  bundles: BundleInventoryItem[];
};

export type BundlePruneRemovedEntry = {
  path: string;
  size_bytes: number;
};

export type BundlePruneResponse = {
  ok: boolean;
  executed: boolean;
  keep_apply: number;
  keep_stage: number;
  bundles_before: number;
  staging_before: number;
  removed_bundles: BundlePruneRemovedEntry[];
  removed_staging: BundlePruneRemovedEntry[];
  bundles_after: number;
  staging_after: number;
  reclaimed_bytes: number;
  last_pruned_at: string;
};

export type DeploymentAudit = {
  profile: DeploymentProfile;
  generated_at: string;
  latest_revision?: {
    version: number;
    status: string;
    created_at: string;
    note: string;
  } | null;
  compared_bundle?: string | null;
  summary: {
    total_files: number;
    changed_files: number;
    unchanged_files: number;
    new_files: number;
  };
  files: Array<{
    name: string;
    target_path: string;
    bytes: number;
    sha256: string;
    previous_sha256?: string | null;
    changed: boolean;
    status: "new" | "changed" | "unchanged";
  }>;
};

export type DeployExecuteResponse = {
  ok: boolean;
  executed: boolean;
  mode: "preview" | "bundle" | "apply" | "rollback";
  profile: DeploymentProfile;
  bundle_root: string;
  host_touched: boolean;
  files_created: string[];
  steps: Array<{
    label: string;
    status: "preview" | "created" | "skipped" | "executed" | "failed";
    detail: string;
  }>;
  warnings: string[];
  next_actions: string[];
};

export type DiagnosticsResponse = {
  draft_config: RelayConfig;
  latest_revision?: {
    version: number;
    status: string;
    created_at: string;
    note: string;
  } | null;
  generated_artifacts: GeneratedArtifact[];
  environment: {
    data_dir: string;
    allowed_origins: string[];
    api_host: string;
    api_port: number;
    host: {
      runtime_dir: string;
      install_root: string;
      bundle_root?: string;
      tools: Record<
        string,
        {
          binary: string;
          path?: string | null;
          available: boolean;
          exit_code?: number;
          preview?: string;
          error?: string;
        }
      >;
      systemd_units: Record<
        string,
        {
          unit: string;
          available: boolean;
          exit_code?: number;
          state?: Record<string, string>;
          error?: string;
        }
      >;
    };
  };
};

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (payload?.detail) {
        detail =
          typeof payload.detail === "string"
            ? payload.detail
            : JSON.stringify(payload.detail);
      }
    } catch {
      // ignore body parse errors
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
  });
  return parseResponse<T>(response);
}

export async function sendJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  return parseResponse<T>(response);
}

export { API_BASE_URL };
