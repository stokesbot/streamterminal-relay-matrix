const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
  services: Array<{ name: string; status: string; detail: string }>;
  recent_events: string[];
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
        detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
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
