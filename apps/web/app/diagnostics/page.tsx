"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchJson, type DiagnosticsResponse } from "@/lib/api";

export default function DiagnosticsPage() {
  const [diagnostics, setDiagnostics] = useState<DiagnosticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const payload = await fetchJson<DiagnosticsResponse>("/api/diagnostics");
        setDiagnostics(payload);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load diagnostics.");
      }
    }

    load();
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-sky-300">Diagnostics</p>
            <h1 className="mt-2 text-3xl font-semibold">Runtime inspection</h1>
            <p className="mt-3 max-w-3xl text-sm text-slate-400">
              Inspect generated artifacts, runtime paths, binary availability, and systemd unit state before any real deployment.
            </p>
          </div>
          <div className="flex gap-3">
            <Link className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800" href="/">
              Dashboard
            </Link>
            <Link className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800" href="/config">
              Configuration
            </Link>
            <Link className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800" href="/deploy">
              Deploy plan
            </Link>
          </div>
        </header>

        {error ? (
          <section className="rounded-2xl border border-rose-900 bg-rose-950/40 p-5 text-sm text-rose-200">
            {error}
          </section>
        ) : null}

        {diagnostics ? (
          <>
            <section className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Latest revision</div>
                <div className="mt-3 text-lg font-semibold text-slate-100">
                  {diagnostics.latest_revision ? `#${diagnostics.latest_revision.version}` : "No revision yet"}
                </div>
                <div className="mt-2 text-sm text-slate-400">{diagnostics.latest_revision?.note ?? "Apply a draft to capture a revision snapshot."}</div>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Runtime dir</div>
                <div className="mt-3 break-all text-sm text-slate-200">{diagnostics.environment.host.runtime_dir}</div>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Install root</div>
                <div className="mt-3 break-all text-sm text-slate-200">{diagnostics.environment.host.install_root}</div>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                <h2 className="text-lg font-semibold">Host tools</h2>
                <div className="mt-4 space-y-3">
                  {Object.entries(diagnostics.environment.host.tools).map(([name, tool]) => (
                    <div key={name} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <div className="font-medium text-slate-100">{name}</div>
                          <div className="mt-1 text-xs text-slate-400">{tool.path ?? tool.binary}</div>
                        </div>
                        <span className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${tool.available ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"}`}>
                          {tool.available ? "available" : "missing"}
                        </span>
                      </div>
                      {tool.preview ? (
                        <pre className="mt-3 whitespace-pre-wrap text-xs text-slate-300">{tool.preview}</pre>
                      ) : null}
                      {tool.error ? <div className="mt-3 text-xs text-rose-300">{tool.error}</div> : null}
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                <h2 className="text-lg font-semibold">Systemd unit state</h2>
                <div className="mt-4 space-y-3">
                  {Object.entries(diagnostics.environment.host.systemd_units).map(([unit, snapshot]) => (
                    <div key={unit} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                      <div className="font-medium text-slate-100">{unit}</div>
                      <div className="mt-2 text-sm text-slate-300">
                        LoadState: {snapshot.state?.LoadState ?? "unknown"} · ActiveState: {snapshot.state?.ActiveState ?? "unknown"} · SubState: {snapshot.state?.SubState ?? "unknown"}
                      </div>
                      {snapshot.error ? <div className="mt-2 text-xs text-rose-300">{snapshot.error}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
              <h2 className="text-lg font-semibold">Generated artifacts</h2>
              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                {diagnostics.generated_artifacts.map((artifact) => (
                  <div key={artifact.name} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                    <div className="font-medium text-slate-100">{artifact.name}</div>
                    <div className="mt-1 break-all text-xs text-slate-400">{artifact.path}</div>
                    <pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap text-xs text-slate-300">
                      {artifact.content}
                    </pre>
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}
