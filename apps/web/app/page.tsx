"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchJson, type RelayConfig, type RuntimeStatus } from "@/lib/api";

type DashboardState = {
  runtime?: RuntimeStatus;
  config?: RelayConfig;
  error?: string;
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
      <div className={`mt-3 inline-flex rounded-full px-3 py-1 text-sm font-medium ${colorMap[value] ?? colorMap.unknown}`}>
        {value}
      </div>
    </div>
  );
}

export default function Home() {
  const [state, setState] = useState<DashboardState>({});

  useEffect(() => {
    async function load() {
      try {
        const [runtime, config] = await Promise.all([
          fetchJson<RuntimeStatus>("/api/runtime/status"),
          fetchJson<RelayConfig>("/api/config"),
        ]);
        setState({ runtime, config });
      } catch (error) {
        setState({
          error: error instanceof Error ? error.message : "Unable to reach API",
        });
      }
    }

    load();
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto flex max-w-6xl flex-col gap-8">
        <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl shadow-slate-950/50 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-sky-300">Prototype</p>
            <h1 className="mt-2 text-3xl font-semibold">StreamTerminal Relay Matrix</h1>
            <p className="mt-3 max-w-2xl text-sm text-slate-400">
              Control plane scaffold for MediaMTX + stream-failover-relay.
              This first build wires a real Next.js frontend to a FastAPI backend
              with draft configuration and mocked runtime status.
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
              href="/config"
            >
              Open configuration
            </Link>
          </div>
        </header>

        {state.error ? (
          <section className="rounded-2xl border border-rose-900 bg-rose-950/40 p-5 text-sm text-rose-200">
            API unavailable: {state.error}. Start the FastAPI app on port 8000 to
            populate live data.
          </section>
        ) : null}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatusPill label="Active source" value={state.runtime?.active_source ?? "unknown"} />
          <StatusPill label="Primary" value={state.runtime?.primary_state ?? "unknown"} />
          <StatusPill label="Backup" value={state.runtime?.backup_state ?? "unknown"} />
          <StatusPill label="Output" value={state.runtime?.output_state ?? "unknown"} />
        </section>

        <section className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-lg font-semibold">Current pipeline</h2>
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
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-lg font-semibold">Services</h2>
            <div className="mt-4 space-y-3">
              {(state.runtime?.services ?? []).map((service) => (
                <div
                  key={service.name}
                  className="rounded-xl border border-slate-800 bg-slate-950/70 p-4"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="font-medium text-slate-100">{service.name}</div>
                      <div className="mt-1 text-sm text-slate-400">{service.detail}</div>
                    </div>
                    <span className="rounded-full bg-slate-800 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-300">
                      {service.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

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
