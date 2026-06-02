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

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export { API_BASE_URL };
