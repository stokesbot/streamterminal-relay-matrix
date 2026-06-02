"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  fetchJson,
  sendJson,
  type DiagnosticsResponse,
  type InstallResult,
  type RelayConfig,
  type RuntimeStatus,
  type ServiceAction,
  type ServiceActionResult,
  type ServiceLogsResponse,
  type ServiceName,
  type SmokeResponse,
} from "@/lib/api";

type DashboardState = {
  runtime?: RuntimeStatus;
  config?: RelayConfig;
  diagnostics?: DiagnosticsResponse;
  smoke?: SmokeResponse;
  error?: string;
};

type ActionState = {
  message?: string;
  error?: string;
  loading: boolean;
};

function StatusPill({ label, value }: { label: string; value: string }) {
  const colorMap: Record<string, string> = {
    healthy: "bg-emerald-500/20 text-emerald-300",
    connected: "bg-emerald-500/20 text-emerald-300",
    running: "bg-emerald-500/20 text-emerald-300",
    down: "bg-rose-500/20 text-rose-300",
    disconnected: "bg-rose-500/20 text-rose-300",
    stopped: "bg-rose-500/20 text-rose-300",
    unknown: "bg-slate-500/20 text-slate-300",
    primary: "bg-sky-500/20 text-sky-300",
    backup: "bg-amber-500/20 text-amber-300",
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{label}</div>
      <div
        className={`mt-3 inline-flex rounded-full px-3 py-1 text-sm font-medium ${colorMap[value] ?? colorMap.unknown}`}
      >
        {value}
      </div>
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  disabled,
  tone = "default",
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: "default" | "primary";
}) {
  return (
    <button
      className={
        tone === "primary"
          ? "rounded-lg bg-sky-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:opacity-50"
          : "rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
      }
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

export default function Home() {
  const [state, setState] = useState<DashboardState>({});
  const [actionState, setActionState] = useState<ActionState>({ loading: false });
  const [logs, setLogs] = useState<Partial<Record<ServiceName, ServiceLogsResponse>>>({});

  const load = useCallback(async () => {
    try {
      const [runtime, config, diagnostics, smoke] = await Promise.all([
        fetchJson<RuntimeStatus>("/api/runtime/status"),
        fetchJson<RelayConfig>("/api/config"),
        fetchJson<DiagnosticsResponse>("/api/diagnostics"),
        fetchJson<SmokeResponse>("/api/runtime/smoke"),
      ]);
      setState({ runtime, config, diagnostics, smoke });
    } catch (error) {
      setState({
        error: error instanceof Error ? error.message : "Unable to reach API",
      });
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function initialLoad() {
      try {
        const [runtime, config, diagnostics, smoke] = await Promise.all([
          fetchJson<RuntimeStatus>("/api/runtime/status"),
          fetchJson<RelayConfig>("/api/config"),
          fetchJson<DiagnosticsResponse>("/api/diagnostics"),
          fetchJson<SmokeResponse>("/api/runtime/smoke"),
        ]);

        if (!cancelled) {
          setState({ runtime, config, diagnostics, smoke });
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            error: error instanceof Error ? error.message : "Unable to reach API",
          });
        }
      }
    }

    void initialLoad();

    return () => {
      cancelled = true;
    };
  }, []);

  async function runControlAction(label: string, action: () => Promise<string>) {
    setActionState({ loading: true });
    try {
      const message = await action();
      setActionState({ loading: false, message });
      await load();
    } catch (error) {
      setActionState({
        loading: false,
        error: error instanceof Error ? error.message : `${label} failed`,
      });
    }
  }

  async function refreshLogs(service: ServiceName) {
    try {
      const payload = await fetchJson<ServiceLogsResponse>(`/api/services/${service}/logs?lines=20`);
      setLogs((current) => ({ ...current, [service]: payload }));
    } catch (error) {
      setActionState({
        loading: false,
        error: error instanceof Error ? error.message : `Unable to load logs for ${service}`,
      });
    }
  }

  async function performServiceAction(service: ServiceName, action: ServiceAction, execute: boolean) {
    return runControlAction(`${service} ${action}`, async () => {
      const payload = await sendJson<ServiceActionResult>(
        `/api/services/${service}/action`,
        "POST",
        { action, execute },
      );
      return payload.executed
        ? `${service} ${action} finished with exit code ${payload.exit_code}.`
        : `${service} ${action} dry-run prepared: ${payload.command.join(" ")}`;
    });
  }

  async function applyDraft() {
    return runControlAction("Apply draft", async () => {
      const payload = await sendJson<{ version: number; note: string }>("/api/config/apply", "POST");
      return `Applied draft as revision ${payload.version}. ${payload.note}`;
    });
  }

  async function installRuntime() {
    return runControlAction("Stage install", async () => {
      const payload = await sendJson<InstallResult>("/api/runtime/install", "POST");
      return `Staged ${payload.artifacts.length} runtime files under ${payload.installed_to}.`;
    });
  }

  async function runSmoke() {
    return runControlAction("Run smoke", async () => {
      const payload = await fetchJson<SmokeResponse>("/api/runtime/smoke");
      setState((current) => ({ ...current, smoke: payload }));
      const total = payload.summary.pass_count + payload.summary.warn_count + payload.summary.fail_count;
      return `Smoke finished: ${payload.summary.pass_count}/${total} pass, ${payload.summary.fail_count} fail.`;
    });
  }

  const latestRevision = state.diagnostics?.latest_revision;
  const hostTools = state.diagnostics?.environment.host.tools ?? {};
  const systemdUnits = state.diagnostics?.environment.host.systemd_units ?? {};

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-8">
        <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl shadow-slate-950/50 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-sky-300">Prototype</p>
            <h1 className="mt-2 text-3xl font-semibold">StreamTerminal Relay Matrix</h1>
            <p className="mt-3 max-w-2xl text-sm text-slate-400">
              Local control-plane prototype for MediaMTX + stream-failover-relay with
              install staging, service controls, diagnostics, and operator log access.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
              href="/config"
            >
              Open configuration
            </Link>
            <Link
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
              href="/diagnostics"
            >
              Open diagnostics
            </Link>
            <Link
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
              href="/deploy"
            >
              Open deployment plan
            </Link>
          </div>
        </header>

        {state.error ? (
          <section className="rounded-2xl border border-rose-900 bg-rose-950/40 p-5 text-sm text-rose-200">
            API unavailable: {state.error}. Start the FastAPI app on port 8000 to populate live data.
          </section>
        ) : null}

        {actionState.message ? (
          <section className="rounded-2xl border border-emerald-900 bg-emerald-950/30 p-5 text-sm text-emerald-200">
            {actionState.message}
          </section>
        ) : null}

        {actionState.error ? (
          <section className="rounded-2xl border border-rose-900 bg-rose-950/40 p-5 text-sm text-rose-200">
            {actionState.error}
          </section>
        ) : null}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatusPill label="Active source" value={state.runtime?.active_source ?? "unknown"} />
          <StatusPill label="Primary" value={state.runtime?.primary_state ?? "unknown"} />
          <StatusPill label="Backup" value={state.runtime?.backup_state ?? "unknown"} />
          <StatusPill label="Output" value={state.runtime?.output_state ?? "unknown"} />
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-lg font-semibold">Current pipeline</h2>
              <span className="text-xs uppercase tracking-[0.2em] text-slate-400">
                {state.config?.channel_name ?? "No channel"}
              </span>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              {[
                ["Primary", state.config?.primary_input.url],
                ["Backup", state.config?.backup_input.url],
                ["Output", state.config?.output.url],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{label}</div>
                  <div className="mt-3 break-all text-sm text-slate-200">{value ?? "—"}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Latest revision</div>
                <div className="mt-3 text-sm text-slate-200">
                  {latestRevision ? `#${latestRevision.version} · ${latestRevision.status}` : "No revision yet"}
                </div>
                <div className="mt-2 text-xs text-slate-400">{latestRevision?.note ?? "Apply a draft to create a revision."}</div>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Install root</div>
                <div className="mt-3 break-all text-sm text-slate-200">
                  {state.diagnostics?.environment.host.install_root ?? "—"}
                </div>
                <div className="mt-2 text-xs text-slate-400">Generated service files are staged here before real deployment.</div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-lg font-semibold">Operator actions</h2>
            <div className="mt-4 flex flex-wrap gap-3">
              <ActionButton disabled={actionState.loading} label="Apply draft" onClick={applyDraft} tone="primary" />
              <ActionButton disabled={actionState.loading} label="Stage install" onClick={installRuntime} />
              <ActionButton
                disabled={actionState.loading}
                label="Daemon reload (dry-run)"
                onClick={() => performServiceAction("mediamtx", "daemon-reload", false)}
              />
              <ActionButton disabled={actionState.loading} label="Run smoke" onClick={runSmoke} />
            </div>
            <p className="mt-4 text-sm text-slate-400">
              Service buttons below support dry-run previews and direct execution against the local host.
            </p>
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-lg font-semibold">Services</h2>
            <div className="mt-4 space-y-4">
              {(state.runtime?.services ?? []).map((service) => (
                <div key={service.name} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                  <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                    <div>
                      <div className="font-medium text-slate-100">{service.name}</div>
                      <div className="mt-1 text-sm text-slate-400">{service.detail}</div>
                    </div>
                    <span className="rounded-full bg-slate-800 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-300">
                      {service.status}
                    </span>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <ActionButton
                      disabled={actionState.loading}
                      label="Restart (dry-run)"
                      onClick={() => performServiceAction(service.name as ServiceName, "restart", false)}
                    />
                    <ActionButton
                      disabled={actionState.loading}
                      label="Restart"
                      onClick={() => performServiceAction(service.name as ServiceName, "restart", true)}
                    />
                    <ActionButton
                      disabled={actionState.loading}
                      label="Status"
                      onClick={() => performServiceAction(service.name as ServiceName, "status", true)}
                    />
                    <ActionButton
                      disabled={actionState.loading}
                      label="Logs"
                      onClick={() => refreshLogs(service.name as ServiceName)}
                    />
                  </div>
                  {logs[service.name as ServiceName] ? (
                    <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950 p-4">
                      <div className="text-xs uppercase tracking-[0.2em] text-slate-400">
                        Latest logs · exit {logs[service.name as ServiceName]?.exit_code ?? "—"}
                      </div>
                      <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap text-xs text-slate-300">
                        {(logs[service.name as ServiceName]?.lines ?? []).join("\n") || "No log lines returned."}
                      </pre>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-lg font-semibold">Host tooling snapshot</h2>
            <div className="mt-4 space-y-3">
              {Object.entries(hostTools).map(([name, tool]) => (
                <div key={name} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="font-medium text-slate-100">{name}</div>
                      <div className="mt-1 text-xs text-slate-400">{tool.path ?? tool.binary}</div>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${tool.available ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"}`}
                    >
                      {tool.available ? "available" : "missing"}
                    </span>
                  </div>
                  {tool.preview ? (
                    <pre className="mt-3 whitespace-pre-wrap text-xs text-slate-300">{tool.preview}</pre>
                  ) : null}
                </div>
              ))}
            </div>
            <div className="mt-6 rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Systemd units</div>
              <div className="mt-3 space-y-3 text-sm text-slate-300">
                {Object.entries(systemdUnits).map(([unit, snapshot]) => (
                  <div key={unit} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                    <div className="font-medium text-slate-200">{unit}</div>
                    <div className="mt-1 text-xs text-slate-400">
                      LoadState: {snapshot.state?.LoadState ?? "unknown"} · ActiveState: {snapshot.state?.ActiveState ?? "unknown"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {state.smoke ? (
          <section
            className={`rounded-2xl border p-6 ${state.smoke.ok ? "border-emerald-900 bg-emerald-950/20" : "border-amber-900 bg-amber-950/20"}`}
            data-testid="live-smoke-section"
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-lg font-semibold">Live smoke</h2>
                <p className="mt-2 text-sm text-slate-300">
                  One-shot probe of mediamtx, the relay, both input paths, and the output destination.
                </p>
                <p className="mt-2 text-xs text-slate-500">Generated at {state.smoke.generated_at}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-4">
                <StatusPill label="Smoke" value={state.smoke.ok ? "ok" : "failing"} />
                <StatusPill label="Pass" value={String(state.smoke.summary.pass_count)} />
                <StatusPill label="Warn" value={String(state.smoke.summary.warn_count)} />
                <StatusPill label="Fail" value={String(state.smoke.summary.fail_count)} />
              </div>
            </div>
            <div className="mt-5 grid gap-3 xl:grid-cols-2">
              {state.smoke.checks.map((check) => (
                <div
                  key={`${check.name}-${check.detail}`}
                  className="rounded-xl border border-slate-800 bg-slate-950/70 p-4"
                  data-testid="smoke-check"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div className="font-medium text-slate-100">{check.name}</div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${
                        check.status === "pass"
                          ? "bg-emerald-950 text-emerald-200"
                          : check.status === "warn"
                            ? "bg-amber-950 text-amber-200"
                            : "bg-rose-950 text-rose-200"
                      }`}
                    >
                      {check.status}
                    </span>
                  </div>
                  <div className="mt-3 text-sm text-slate-300">{check.detail}</div>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="text-lg font-semibold">Recent events</h2>
          <ul className="mt-4 space-y-3 text-sm text-slate-300">
            {(state.runtime?.recent_events ?? []).map((event) => (
              <li key={event} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                {event}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  );
}
