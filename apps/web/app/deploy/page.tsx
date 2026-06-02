"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  fetchJson,
  sendJson,
  type DeployExecuteResponse,
  type DeploymentAudit,
  type DeploymentPlan,
  type DeploymentProfile,
  type DeploymentProfileId,
  type SavedDeploymentProfileRequest,
} from "@/lib/api";

const phases: Array<DeploymentPlan["commands"][number]["phase"]> = [
  "prepare",
  "copy",
  "activate",
  "verify",
];

const defaultTargetForm: SavedDeploymentProfileRequest = {
  label: "",
  description: "",
  run_on: "remote",
  target_host: "",
  target_user: "relayops",
  path_roots: {
    config_dir: "/etc/streamterminal-relay-matrix",
    bin_dir: "/usr/local/bin",
    systemd_dir: "/etc/systemd/system",
  },
  notes: ["Review SSH access and rollback steps before activation."],
  secret_placeholders: [
    "Create the live env file on-host and keep secrets outside git.",
  ],
};

export default function DeployPage() {
  const [profiles, setProfiles] = useState<DeploymentProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<DeploymentProfileId>("local-dev");
  const [plan, setPlan] = useState<DeploymentPlan | null>(null);
  const [audit, setAudit] = useState<DeploymentAudit | null>(null);
  const [execution, setExecution] = useState<DeployExecuteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningPreview, setRunningPreview] = useState(false);
  const [runningBundle, setRunningBundle] = useState(false);
  const [savingTarget, setSavingTarget] = useState(false);
  const [targetForm, setTargetForm] = useState<SavedDeploymentProfileRequest>(defaultTargetForm);

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

    async function loadDeploymentData() {
      setLoading(true);
      try {
        const [planPayload, auditPayload] = await Promise.all([
          fetchJson<DeploymentPlan>(`/api/deploy/plan?profile_id=${selectedProfile}`),
          fetchJson<DeploymentAudit>(`/api/deploy/audit?profile_id=${selectedProfile}`),
        ]);
        if (!cancelled) {
          setPlan(planPayload);
          setAudit(auditPayload);
          setExecution(null);
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

    void loadDeploymentData();
    return () => {
      cancelled = true;
    };
  }, [selectedProfile]);

  const groupedCommands = useMemo(() => {
    if (!plan) {
      return [];
    }

    return phases.map((phase) => ({
      phase,
      commands: plan.commands.filter((command) => command.phase === phase),
    }));
  }, [plan]);

  async function reloadProfiles(nextProfileId?: string) {
    const payload = await fetchJson<DeploymentProfile[]>("/api/deploy/profiles");
    setProfiles(payload);
    if (nextProfileId) {
      setSelectedProfile(nextProfileId);
    }
  }

  async function runExecution(execute: boolean) {
    if (execute) {
      setRunningBundle(true);
    } else {
      setRunningPreview(true);
    }

    try {
      const payload = await sendJson<DeployExecuteResponse>("/api/deploy/execute", "POST", {
        profile_id: selectedProfile,
        execute,
      });
      setExecution(payload);
      setError(null);
      const auditPayload = await fetchJson<DeploymentAudit>(`/api/deploy/audit?profile_id=${selectedProfile}`);
      setAudit(auditPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run deployment action.");
    } finally {
      if (execute) {
        setRunningBundle(false);
      } else {
        setRunningPreview(false);
      }
    }
  }

  async function saveTargetProfile() {
    setSavingTarget(true);
    try {
      const saved = await sendJson<DeploymentProfile>("/api/deploy/targets", "POST", targetForm);
      await reloadProfiles(saved.id);
      setTargetForm(defaultTargetForm);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save target profile.");
    } finally {
      setSavingTarget(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-sky-300">Deployment planning</p>
            <h1 className="mt-2 text-3xl font-semibold">Staging, audit, and rollout workflow</h1>
            <p className="mt-3 max-w-3xl text-sm text-slate-400">
              Preview staged artifacts, save host targets outside git-tracked code, audit checksums, and generate safe deploy bundles before touching a real host.
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

        <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
              <div>
                <label className="text-sm text-slate-400">Deployment profile</label>
                <select
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
                  value={selectedProfile}
                  onChange={(event) => setSelectedProfile(event.target.value)}
                >
                  {profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.label} {profile.source === "saved" ? "(saved)" : "(builtin)"}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={runningPreview}
                  onClick={() => void runExecution(false)}
                  type="button"
                >
                  {runningPreview ? "Previewing..." : "Preview safe execute"}
                </button>
                <button
                  className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={runningBundle}
                  onClick={() => void runExecution(true)}
                  type="button"
                >
                  {runningBundle ? "Generating bundle..." : "Generate deploy bundle"}
                </button>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Saved target profile</p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <input
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
                placeholder="Target label"
                value={targetForm.label}
                onChange={(event) => setTargetForm({ ...targetForm, label: event.target.value })}
              />
              <input
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
                placeholder="Target host"
                value={targetForm.target_host}
                onChange={(event) => setTargetForm({ ...targetForm, target_host: event.target.value })}
              />
              <input
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400 md:col-span-2"
                placeholder="Short description"
                value={targetForm.description}
                onChange={(event) => setTargetForm({ ...targetForm, description: event.target.value })}
              />
              <input
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
                placeholder="Target user"
                value={targetForm.target_user}
                onChange={(event) => setTargetForm({ ...targetForm, target_user: event.target.value })}
              />
              <select
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
                value={targetForm.run_on}
                onChange={(event) => setTargetForm({ ...targetForm, run_on: event.target.value as "local" | "remote" })}
              >
                <option value="remote">remote</option>
                <option value="local">local</option>
              </select>
            </div>
            <button
              className="mt-4 rounded-lg border border-emerald-700 px-4 py-2 text-sm text-emerald-200 hover:bg-emerald-950/40 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={savingTarget}
              onClick={() => void saveTargetProfile()}
              type="button"
            >
              {savingTarget ? "Saving target..." : "Save target profile"}
            </button>
          </div>
        </section>

        {error ? (
          <section className="rounded-2xl border border-rose-900 bg-rose-950/40 p-5 text-sm text-rose-200">
            {error}
          </section>
        ) : null}

        {loading ? (
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-300">
            Loading deployment plan and audit...
          </section>
        ) : null}

        {execution ? (
          <section className="rounded-2xl border border-emerald-900 bg-emerald-950/30 p-6">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-emerald-300">Safe deploy execution</p>
                <h2 className="mt-2 text-xl font-semibold text-slate-100">
                  {execution.executed ? "Bundle written locally" : "Preview generated"}
                </h2>
                <p className="mt-2 text-sm text-slate-300">Bundle root: {execution.bundle_root}</p>
                <p className="mt-1 text-sm text-slate-400">Remote touched: {execution.remote_touched ? "yes" : "no"}</p>
              </div>
              <div className="rounded-xl border border-emerald-800 bg-slate-950/70 px-4 py-3 text-sm text-emerald-100">
                Mode: {execution.mode}
              </div>
            </div>
            <div className="mt-5 grid gap-4 xl:grid-cols-[1fr_1fr]">
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">Steps</h3>
                <ul className="mt-3 space-y-3 text-sm text-slate-200">
                  {execution.steps.map((step) => (
                    <li key={`${step.label}-${step.detail}`} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                      <div className="font-medium text-slate-100">{step.label}</div>
                      <div className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">{step.status}</div>
                      <div className="mt-2 text-slate-300">{step.detail}</div>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">Next actions</h3>
                <ul className="mt-3 space-y-3 text-sm text-slate-200">
                  {execution.next_actions.map((action) => (
                    <li key={action} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                      {action}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </section>
        ) : null}

        {audit ? (
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-lg font-semibold">Deployment audit</h2>
                <p className="mt-2 text-sm text-slate-400">
                  Compare current staged files against the latest bundle for this profile.
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  Compared bundle: {audit.compared_bundle ?? "No earlier bundle found for this profile"}
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-4">
                <AuditStat label="Total" value={String(audit.summary.total_files)} />
                <AuditStat label="Changed" value={String(audit.summary.changed_files)} />
                <AuditStat label="Unchanged" value={String(audit.summary.unchanged_files)} />
                <AuditStat label="New" value={String(audit.summary.new_files)} />
              </div>
            </div>
            <div className="mt-5 grid gap-3 xl:grid-cols-2">
              {audit.files.map((file) => (
                <div key={file.target_path} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="font-medium text-slate-100">{file.name}</div>
                      <div className="mt-1 break-all text-xs text-slate-400">{file.target_path}</div>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${file.status === "changed" ? "bg-amber-950 text-amber-200" : file.status === "new" ? "bg-sky-950 text-sky-200" : "bg-emerald-950 text-emerald-200"}`}>
                      {file.status}
                    </span>
                  </div>
                  <div className="mt-4 space-y-2 text-xs text-slate-300">
                    <div>Current: {file.sha256}</div>
                    <div>Previous: {file.previous_sha256 ?? "none"}</div>
                    <div>{file.bytes} bytes</div>
                  </div>
                </div>
              ))}
            </div>
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

              <div className="space-y-4">
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
                </div>

                {plan.secret_templates.map((template) => (
                  <div key={template.name} className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                    <h2 className="text-lg font-semibold">Env-file template</h2>
                    <div className="mt-3 text-sm text-slate-300">Live file: {template.live_path}</div>
                    <div className="mt-1 text-sm text-slate-400">Example file: {template.example_path}</div>
                    <pre className="mt-4 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
                      {template.example_content}
                    </pre>
                    <div className="mt-4 text-xs uppercase tracking-[0.2em] text-slate-400">Masked current draft values</div>
                    <div className="mt-2 space-y-2 text-sm text-slate-300">
                      {Object.entries(template.masked_current_values).map(([key, value]) => (
                        <div key={key} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                          <span className="font-medium text-slate-100">{key}</span>: {value}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}

                {plan.warnings.length > 0 ? (
                  <div className="rounded-2xl border border-rose-900 bg-rose-950/30 p-6">
                    <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-rose-200">Warnings</h3>
                    <ul className="mt-3 space-y-3 text-sm text-rose-100">
                      {plan.warnings.map((warning) => (
                        <li key={warning} className="rounded-xl border border-rose-900 bg-rose-950/40 p-4">
                          {warning}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
              <h2 className="text-lg font-semibold">Execution plan</h2>
              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                {groupedCommands.map(({ phase, commands }) => (
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
                ))}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}

function AuditStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-center">
      <div className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="mt-2 text-xl font-semibold text-slate-100">{value}</div>
    </div>
  );
}
