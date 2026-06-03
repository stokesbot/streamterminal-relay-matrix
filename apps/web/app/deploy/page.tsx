"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  fetchJson,
  sendJson,
  type DeployExecuteResponse,
  type DeploymentAudit,
  type DeploymentPlan,
  type DeploymentPreflight,
  type DeploymentProfile,
  type HostSnapshotListResponse,
  type HostSnapshotRestoreResult,
  type HostSnapshotSummary,
} from "@/lib/api";

const phases: Array<DeploymentPlan["commands"][number]["phase"]> = [
  "prepare",
  "copy",
  "activate",
  "verify",
];

export default function DeployPage() {
  const [profile, setProfile] = useState<DeploymentProfile | null>(null);
  const [preflight, setPreflight] = useState<DeploymentPreflight | null>(null);
  const [plan, setPlan] = useState<DeploymentPlan | null>(null);
  const [audit, setAudit] = useState<DeploymentAudit | null>(null);
  const [snapshots, setSnapshots] = useState<HostSnapshotSummary[]>([]);
  const [execution, setExecution] = useState<DeployExecuteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningPreflight, setRunningPreflight] = useState(false);
  const [runningPreview, setRunningPreview] = useState(false);
  const [runningApply, setRunningApply] = useState(false);
  const [runningRollback, setRunningRollback] = useState(false);
  const [runningBundle, setRunningBundle] = useState(false);
  const [restoreBanner, setRestoreBanner] = useState<string | null>(null);
  const [runningRestoreId, setRunningRestoreId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadDeploymentData() {
      setLoading(true);
      try {
        const [
          profilesPayload,
          preflightPayload,
          planPayload,
          auditPayload,
          snapshotsPayload,
        ] = await Promise.all([
          fetchJson<DeploymentProfile[]>("/api/deploy/profiles"),
          fetchJson<DeploymentPreflight>("/api/deploy/preflight?profile_id=local-system"),
          fetchJson<DeploymentPlan>("/api/deploy/plan?profile_id=local-system"),
          fetchJson<DeploymentAudit>("/api/deploy/audit?profile_id=local-system"),
          fetchJson<HostSnapshotListResponse>("/api/deploy/host-snapshots"),
        ]);
        if (!cancelled) {
          setProfile(profilesPayload[0] ?? null);
          setPreflight(preflightPayload);
          setPlan(planPayload);
          setAudit(auditPayload);
          setSnapshots(snapshotsPayload.snapshots ?? []);
          setExecution(null);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load local deployment workflow.");
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
  }, []);

  const groupedCommands = useMemo(() => {
    if (!plan) {
      return [];
    }

    return phases.map((phase) => ({
      phase,
      commands: plan.commands.filter((command) => command.phase === phase),
    }));
  }, [plan]);

  async function refreshDeploymentState() {
    const [preflightPayload, planPayload, auditPayload] = await Promise.all([
      fetchJson<DeploymentPreflight>("/api/deploy/preflight?profile_id=local-system"),
      fetchJson<DeploymentPlan>("/api/deploy/plan?profile_id=local-system"),
      fetchJson<DeploymentAudit>("/api/deploy/audit?profile_id=local-system"),
    ]);
    setPreflight(preflightPayload);
    setPlan(planPayload);
    setAudit(auditPayload);
  }

  async function runPreflight() {
    setRunningPreflight(true);
    try {
      const payload = await fetchJson<DeploymentPreflight>("/api/deploy/preflight?profile_id=local-system");
      setPreflight(payload);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run local preflight.");
    } finally {
      setRunningPreflight(false);
    }
  }

  async function runExecution(action: "preview" | "bundle" | "apply" | "rollback") {
    if (action === "preview") {
      setRunningPreview(true);
    } else if (action === "bundle") {
      setRunningBundle(true);
    } else if (action === "apply") {
      setRunningApply(true);
    } else {
      setRunningRollback(true);
    }

    try {
      const payload = await sendJson<DeployExecuteResponse>("/api/deploy/execute", "POST", {
        profile_id: "local-system",
        execute: action !== "preview",
        action,
      });
      setExecution(payload);
      await refreshDeploymentState();
      // Re-pull the snapshot list because apply/rollback capture a new snapshot.
      const snapshotList = await fetchJson<HostSnapshotListResponse>("/api/deploy/host-snapshots");
      setSnapshots(snapshotList.snapshots ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run local deployment action.");
    } finally {
      if (action === "preview") {
        setRunningPreview(false);
      } else if (action === "bundle") {
        setRunningBundle(false);
      } else if (action === "apply") {
        setRunningApply(false);
      } else {
        setRunningRollback(false);
      }
    }
  }

  async function restoreSnapshot(snapshot: HostSnapshotSummary) {
    if (typeof window !== "undefined" && !window.confirm(
      `Restore snapshot ${snapshot.id} (${snapshot.file_count} files, ${snapshot.total_bytes} bytes)? This will overwrite the live /etc/streamterminal-relay-matrix, /etc/systemd/system, and /usr/local/bin files.`,
    )) {
      return;
    }
    setRunningRestoreId(snapshot.id);
    setRestoreBanner(null);
    try {
      const payload = await sendJson<HostSnapshotRestoreResult>(
        "/api/deploy/restore-snapshot",
        "POST",
        { snapshot_id: snapshot.id, execute: true },
      );
      const restoredCount = payload.restored?.length ?? 0;
      setRestoreBanner(
        `Restored snapshot ${snapshot.id} (${restoredCount} files) onto ${payload.host_root}.`,
      );
      await refreshDeploymentState();
    } catch (err) {
      setRestoreBanner(
        err instanceof Error ? `Restore failed: ${err.message}` : "Unable to restore snapshot.",
      );
    } finally {
      setRunningRestoreId(null);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-sky-300">Local install workflow</p>
            <h1 className="mt-2 text-3xl font-semibold">Install and operate on this Linux host</h1>
            <p className="mt-3 max-w-3xl text-sm text-slate-400">
              This page is local-only. It runs preflight checks, prepares configs, env templates, systemd units, audit hashes, and can now apply or roll back the relay stack directly on the same Linux machine where the control plane runs.
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

        <section className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Workflow target</div>
                <div className="mt-2 text-lg font-semibold text-slate-100">
                  {profile ? `${profile.label} · ${profile.target_user}@${profile.target_host}` : "Loading local profile..."}
                </div>
                <div className="mt-2 text-sm text-slate-400">
                  {profile?.description ?? "Preparing local deployment profile."}
                </div>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={runningPreflight}
                  onClick={() => void runPreflight()}
                  type="button"
                >
                  {runningPreflight ? "Checking..." : "Run local preflight"}
                </button>
                <button
                  className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={runningPreview}
                  onClick={() => void runExecution("preview")}
                  type="button"
                >
                  {runningPreview ? "Previewing..." : "Preview local apply"}
                </button>
                <button
                  className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={runningApply}
                  onClick={() => void runExecution("apply")}
                  type="button"
                >
                  {runningApply ? "Applying..." : "True local apply"}
                </button>
                <button
                  className="rounded-lg border border-amber-700 px-4 py-2 text-sm text-amber-100 hover:bg-amber-950/40 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={runningRollback}
                  onClick={() => void runExecution("rollback")}
                  type="button"
                >
                  {runningRollback ? "Rolling back..." : "Local rollback"}
                </button>
                <button
                  className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={runningBundle}
                  onClick={() => void runExecution("bundle")}
                  type="button"
                >
                  {runningBundle ? "Generating bundle..." : "Generate local install bundle"}
                </button>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="text-xs uppercase tracking-[0.2em] text-slate-400">What changed</div>
            <ul className="mt-4 space-y-3 text-sm text-slate-300">
              <li className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">Preflight now checks sudo, systemd, required binaries, host paths, rollback readiness, and whether the live relay env file is actually ready for automatic service start.</li>
              <li className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">True local apply can install into /etc and /usr/local/bin, reload systemd, and change service state automatically, while refusing to treat a crash-looping relay or placeholder env file as a success.</li>
              <li className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">Rollback now restores the previous applied local bundle instead of just writing another safe preview package.</li>
            </ul>
          </div>
        </section>

        {error ? (
          <section className="rounded-2xl border border-rose-900 bg-rose-950/40 p-5 text-sm text-rose-200">
            {error}
          </section>
        ) : null}

        {loading ? (
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-300">
            Loading local install workflow...
          </section>
        ) : null}

        {preflight ? (
          <section className={`rounded-2xl border p-6 ${preflight.summary.ok ? "border-emerald-900 bg-emerald-950/20" : "border-amber-900 bg-amber-950/20"}`}>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-lg font-semibold">Local preflight</h2>
                <p className="mt-2 text-sm text-slate-300">
                  Verify that this host can perform a true local apply without any SSH or remote-copy steps.
                </p>
                <p className="mt-2 text-xs text-slate-500">Generated at {preflight.generated_at}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-4">
                <AuditStat label="Ready" value={preflight.summary.ok ? "yes" : "no"} />
                <AuditStat label="Pass" value={String(preflight.summary.pass_count)} />
                <AuditStat label="Warn" value={String(preflight.summary.warn_count)} />
                <AuditStat label="Fail" value={String(preflight.summary.fail_count)} />
              </div>
            </div>
            <div className="mt-5 grid gap-3 xl:grid-cols-2">
              {preflight.checks.map((check) => (
                <div key={`${check.name}-${check.detail}`} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div className="font-medium text-slate-100">{check.name}</div>
                    <span className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${check.status === "pass" ? "bg-emerald-950 text-emerald-200" : check.status === "warn" ? "bg-amber-950 text-amber-200" : "bg-rose-950 text-rose-200"}`}>
                      {check.status}
                    </span>
                  </div>
                  <div className="mt-3 text-sm text-slate-300">{check.detail}</div>
                  {check.command ? <pre className="mt-3 whitespace-pre-wrap text-xs text-slate-500">{check.command}</pre> : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {execution ? (
          <section className={`rounded-2xl border p-6 ${execution.ok ? "border-emerald-900 bg-emerald-950/30" : "border-rose-900 bg-rose-950/30"}`}>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className={`text-xs uppercase tracking-[0.2em] ${execution.ok ? "text-emerald-300" : "text-rose-300"}`}>Local execution result</p>
                <h2 className="mt-2 text-xl font-semibold text-slate-100">
                  {execution.mode === "preview"
                    ? "Preview generated"
                    : execution.mode === "bundle"
                      ? "Bundle written locally"
                      : execution.mode === "apply"
                        ? execution.ok
                          ? "True local apply completed"
                          : "True local apply reported failures"
                        : execution.ok
                          ? "Local rollback completed"
                          : "Local rollback reported failures"}
                </h2>
                <p className="mt-2 text-sm text-slate-300">Bundle root: {execution.bundle_root}</p>
                <p className="mt-1 text-sm text-slate-400">Host touched: {execution.host_touched ? "yes" : "no"}</p>
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
                <h2 className="text-lg font-semibold">Local deployment audit</h2>
                <p className="mt-2 text-sm text-slate-400">
                  Compare current staged files against the latest local install bundle for this host.
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  Compared bundle: {audit.compared_bundle ?? "No earlier local bundle found yet"}
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

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h2 className="text-lg font-semibold">Local host snapshots</h2>
              <p className="mt-2 text-sm text-slate-400">
                Captured automatically before every apply or rollback. Restore one to roll the
                live /etc, /etc/systemd/system, and /usr/local/bin files back to a known state.
              </p>
            </div>
            {restoreBanner ? (
              <div
                data-testid="restore-banner"
                className="rounded-lg border border-emerald-900 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-200"
              >
                {restoreBanner}
              </div>
            ) : null}
          </div>
          {snapshots.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">
              No snapshots yet. Run a local apply to capture one.
            </p>
          ) : (
            <ul className="mt-4 space-y-3 text-sm text-slate-200" data-testid="host-snapshot-list">
              {snapshots
                .slice()
                .reverse()
                .map((snap) => (
                  <li
                    key={snap.id}
                    className="rounded-lg border border-slate-800 bg-slate-950 p-4"
                    data-testid="host-snapshot-row"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="font-mono text-sm text-slate-100">{snap.id}</div>
                        <div className="mt-1 text-xs text-slate-400">
                          trigger={snap.trigger} · created_at={snap.created_at} · files={snap.file_count} ·{" "}
                          bytes={snap.total_bytes}
                        </div>
                        <div className="mt-1 break-all text-xs text-slate-500">{snap.host_root}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => void restoreSnapshot(snap)}
                        disabled={runningRestoreId === snap.id}
                        className="rounded-lg border border-amber-700 bg-amber-950 px-3 py-2 text-xs font-medium uppercase tracking-[0.2em] text-amber-100 hover:bg-amber-900 disabled:opacity-50"
                      >
                        {runningRestoreId === snap.id ? "Restoring..." : "Restore"}
                      </button>
                    </div>
                  </li>
                ))}
            </ul>
          )}
        </section>

        {plan ? (
          <>
            <section className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Local host</div>
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
                <h2 className="text-lg font-semibold">Planned local file map</h2>
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
                      <div className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-400">Local target</div>
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
                  <h2 className="text-lg font-semibold">Host notes</h2>
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
              <h2 className="text-lg font-semibold">Local execution plan</h2>
              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                {groupedCommands.map(({ phase, commands }) => (
                  <div key={phase} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{phase}</div>
                    <div className="mt-4 space-y-3">
                      {commands.map((command) => (
                        <div key={`${phase}-${command.label}`} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                          <div className="font-medium text-slate-100">{command.label}</div>
                          <div className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">local</div>
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
