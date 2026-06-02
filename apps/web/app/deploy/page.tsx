"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  fetchJson,
  type DeploymentPlan,
  type DeploymentProfile,
  type DeploymentProfileId,
} from "@/lib/api";

const phases: Array<DeploymentPlan["commands"][number]["phase"]> = [
  "prepare",
  "copy",
  "activate",
  "verify",
];

export default function DeployPage() {
  const [profiles, setProfiles] = useState<DeploymentProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<DeploymentProfileId>("local-dev");
  const [plan, setPlan] = useState<DeploymentPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadProfiles() {
      try {
        const payload = await fetchJson<DeploymentProfile[]>("/api/deploy/profiles");
        if (!cancelled) {
          setProfiles(payload);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load deployment profiles.");
        }
      }
    }

    void loadProfiles();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadPlan() {
      setLoading(true);
      try {
        const payload = await fetchJson<DeploymentPlan>(`/api/deploy/plan?profile_id=${selectedProfile}`);
        if (!cancelled) {
          setPlan(payload);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load deployment plan.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadPlan();
    return () => {
      cancelled = true;
    };
  }, [selectedProfile]);

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-sky-300">Deployment planning</p>
            <h1 className="mt-2 text-3xl font-semibold">Staging and rollout workflow</h1>
            <p className="mt-3 max-w-3xl text-sm text-slate-400">
              Preview staged artifacts, target paths, activation commands, and deployment notes
              before touching a real host.
            </p>
          </div>
          <div className="flex gap-3">
            <Link className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800" href="/">
              Dashboard
            </Link>
            <Link className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800" href="/diagnostics">
              Diagnostics
            </Link>
          </div>
        </header>

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <label className="text-sm text-slate-400">Deployment profile</label>
          <select
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400 md:max-w-md"
            value={selectedProfile}
            onChange={(event) => setSelectedProfile(event.target.value as DeploymentProfileId)}
          >
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.label}
              </option>
            ))}
          </select>
        </section>

        {error ? (
          <section className="rounded-2xl border border-rose-900 bg-rose-950/40 p-5 text-sm text-rose-200">
            {error}
          </section>
        ) : null}

        {loading ? (
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-300">
            Loading deployment plan...
          </section>
        ) : null}

        {plan ? (
          <>
            <section className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Target host</div>
                <div className="mt-3 text-lg font-semibold text-slate-100">{plan.profile.target_user}@{plan.profile.target_host}</div>
                <div className="mt-2 text-sm text-slate-400">{plan.profile.description}</div>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Staged root</div>
                <div className="mt-3 break-all text-sm text-slate-200">{plan.staged_root}</div>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Latest revision</div>
                <div className="mt-3 text-sm text-slate-200">
                  {plan.latest_revision ? `#${plan.latest_revision.version} · ${plan.latest_revision.status}` : "No applied revision yet"}
                </div>
                <div className="mt-2 text-xs text-slate-400">Generated at {plan.generated_at}</div>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                <h2 className="text-lg font-semibold">Planned file copy map</h2>
                <div className="mt-4 space-y-3">
                  {plan.files.map((file) => (
                    <div key={file.name} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                      <div className="flex items-center justify-between gap-4">
                        <div className="font-medium text-slate-100">{file.name}</div>
                        <span className="rounded-full bg-slate-800 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-300">
                          {file.bytes} bytes
                        </span>
                      </div>
                      <div className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-400">Source</div>
                      <div className="mt-1 break-all text-sm text-slate-300">{file.source_path}</div>
                      <div className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-400">Target</div>
                      <div className="mt-1 break-all text-sm text-slate-300">{file.target_path}</div>
                      <pre className="mt-4 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
                        {file.preview}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                <h2 className="text-lg font-semibold">Profile notes</h2>
                <ul className="mt-4 space-y-3 text-sm text-slate-300">
                  {plan.profile.notes.map((note) => (
                    <li key={note} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                      {note}
                    </li>
                  ))}
                </ul>
                <h3 className="mt-6 text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">Secret handling</h3>
                <ul className="mt-3 space-y-3 text-sm text-amber-200">
                  {plan.profile.secret_placeholders.map((note) => (
                    <li key={note} className="rounded-xl border border-amber-900 bg-amber-950/30 p-4">
                      {note}
                    </li>
                  ))}
                </ul>
                {plan.warnings.length > 0 ? (
                  <>
                    <h3 className="mt-6 text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">Warnings</h3>
                    <ul className="mt-3 space-y-3 text-sm text-rose-200">
                      {plan.warnings.map((warning) => (
                        <li key={warning} className="rounded-xl border border-rose-900 bg-rose-950/30 p-4">
                          {warning}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
              <h2 className="text-lg font-semibold">Execution plan</h2>
              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                {phases.map((phase) => {
                  const commands = plan.commands.filter((command) => command.phase === phase);
                  return (
                    <div key={phase} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                      <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{phase}</div>
                      <div className="mt-4 space-y-3">
                        {commands.map((command) => (
                          <div key={`${phase}-${command.label}`} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                            <div className="font-medium text-slate-100">{command.label}</div>
                            <div className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">{command.run_on}</div>
                            <pre className="mt-3 whitespace-pre-wrap text-xs text-slate-300">{command.command}</pre>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}
