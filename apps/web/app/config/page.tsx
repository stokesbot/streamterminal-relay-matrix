"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  API_BASE_URL,
  sendJson,
  type ApplyResult,
  type InstallResult,
  type RelayConfig,
  type ValidationResult,
} from "@/lib/api";

const defaultConfig: RelayConfig = {
  channel_name: "IBM VS Failover",
  mediamtx_enabled: true,
  relay_enabled: true,
  auto_restart: true,
  primary_input: {
    label: "Primary",
    protocol: "rtmp",
    url: "",
    mode: "pull",
    enabled: true,
  },
  backup_input: {
    label: "Backup",
    protocol: "rtmp",
    url: "",
    mode: "pull",
    enabled: true,
  },
  output: {
    label: "Output",
    protocol: "rtmp",
    url: "",
    mode: "push",
    enabled: true,
  },
};

function EndpointEditor({
  title,
  value,
  onChange,
}: {
  title: string;
  value: RelayConfig["primary_input"];
  onChange: (next: RelayConfig["primary_input"]) => void;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="mt-4 grid gap-3">
        <input
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
          placeholder="Label"
          value={value.label}
          onChange={(event) => onChange({ ...value, label: event.target.value })}
        />
        <select
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
          value={value.protocol}
          onChange={(event) => onChange({ ...value, protocol: event.target.value })}
        >
          {["rtmp", "srt", "rtsp", "udp", "file"].map((protocol) => (
            <option key={protocol} value={protocol}>
              {protocol.toUpperCase()}
            </option>
          ))}
        </select>
        <input
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
          placeholder="URL"
          value={value.url}
          onChange={(event) => onChange({ ...value, url: event.target.value })}
        />
        <select
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
          value={value.mode}
          onChange={(event) => onChange({ ...value, mode: event.target.value })}
        >
          {["pull", "push", "listener", "caller"].map((mode) => (
            <option key={mode} value={mode}>
              {mode}
            </option>
          ))}
        </select>
        <label className="inline-flex items-center gap-2 text-sm text-slate-300">
          <input
            checked={value.enabled}
            type="checkbox"
            onChange={(event) => onChange({ ...value, enabled: event.target.checked })}
          />
          Enabled
        </label>
      </div>
    </div>
  );
}

export default function ConfigPage() {
  const [config, setConfig] = useState<RelayConfig>(defaultConfig);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [status, setStatus] = useState<string>("Loading config...");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/config`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`Load failed: ${response.status}`);
        }
        const payload = (await response.json()) as RelayConfig;
        setConfig(payload);
        setStatus("Loaded draft config from API.");
      } catch {
        setStatus(`API not reachable at ${API_BASE_URL}. Using local defaults.`);
      }
    }

    load();
  }, []);

  const toggles: Array<{
    label: string;
    checked: boolean;
    setValue: (value: boolean) => void;
  }> = useMemo(
    () => [
      {
        label: "MediaMTX enabled",
        checked: config.mediamtx_enabled,
        setValue: (value: boolean) =>
          setConfig({ ...config, mediamtx_enabled: value }),
      },
      {
        label: "Relay enabled",
        checked: config.relay_enabled,
        setValue: (value: boolean) =>
          setConfig({ ...config, relay_enabled: value }),
      },
      {
        label: "Auto restart",
        checked: config.auto_restart,
        setValue: (value: boolean) => setConfig({ ...config, auto_restart: value }),
      },
    ],
    [config],
  );

  async function validateConfig() {
    try {
      const payload = await sendJson<ValidationResult>("/api/config/validate", "POST", config);
      setValidation(payload);
      setStatus(payload.valid ? "Validation passed." : "Validation reported issues.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Validation failed.");
    }
  }

  async function saveDraft() {
    setSaving(true);
    try {
      const payload = await sendJson<RelayConfig>("/api/config/draft", "PUT", config);
      setConfig(payload);
      setStatus("Draft saved to backend.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to save draft.");
    } finally {
      setSaving(false);
    }
  }

  async function applyDraft() {
    setSaving(true);
    try {
      const payload = await sendJson<ApplyResult>("/api/config/apply", "POST");
      setStatus(`Draft applied as revision ${payload.version}. ${payload.note}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to apply draft.");
    } finally {
      setSaving(false);
    }
  }

  async function stageInstall() {
    setSaving(true);
    try {
      const payload = await sendJson<InstallResult>("/api/runtime/install", "POST");
      setStatus(`Install layout staged in ${payload.installed_to}.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to stage install.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-sky-300">Configuration</p>
            <h1 className="mt-2 text-3xl font-semibold">Single-channel prototype</h1>
            <p className="mt-3 max-w-2xl text-sm text-slate-400">
              Edit the draft config, validate it with the backend, apply it to generate
              runtime artifacts, and stage the local install layout without touching a real host yet.
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
              href="/"
            >
              Back to dashboard
            </Link>
            <Link
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
              href="/diagnostics"
            >
              Diagnostics
            </Link>
            <Link
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
              href="/deploy"
            >
              Deploy plan
            </Link>
          </div>
        </header>

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-300">
          {status}
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <label className="text-sm text-slate-400">Channel name</label>
          <input
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-sky-400"
            value={config.channel_name}
            onChange={(event) => setConfig({ ...config, channel_name: event.target.value })}
          />
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {toggles.map((toggle) => (
              <label
                key={toggle.label}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-300"
              >
                <input
                  checked={toggle.checked}
                  type="checkbox"
                  onChange={(event) => toggle.setValue(event.target.checked)}
                />
                {toggle.label}
              </label>
            ))}
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-3">
          <EndpointEditor
            title="Primary input"
            value={config.primary_input}
            onChange={(next) => setConfig({ ...config, primary_input: next })}
          />
          <EndpointEditor
            title="Backup input"
            value={config.backup_input}
            onChange={(next) => setConfig({ ...config, backup_input: next })}
          />
          <EndpointEditor
            title="Output"
            value={config.output}
            onChange={(next) => setConfig({ ...config, output: next })}
          />
        </section>

        <section className="flex flex-wrap gap-3">
          <button
            className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-sky-400"
            onClick={validateConfig}
            type="button"
          >
            Validate draft
          </button>
          <button
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
            disabled={saving}
            onClick={saveDraft}
            type="button"
          >
            {saving ? "Working..." : "Save draft"}
          </button>
          <button
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
            disabled={saving}
            onClick={applyDraft}
            type="button"
          >
            Apply draft
          </button>
          <button
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
            disabled={saving}
            onClick={stageInstall}
            type="button"
          >
            Stage install
          </button>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="text-lg font-semibold">Validation feedback</h2>
          <div className="mt-4 space-y-3 text-sm">
            {validation ? (
              validation.issues.length > 0 ? (
                validation.issues.map((issue) => (
                  <div
                    key={`${issue.level}-${issue.message}`}
                    className="rounded-xl border border-slate-800 bg-slate-950/70 p-4"
                  >
                    <div className="font-medium uppercase tracking-[0.2em] text-slate-400">
                      {issue.level}
                    </div>
                    <div className="mt-2 text-slate-200">{issue.message}</div>
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-emerald-900 bg-emerald-950/30 p-4 text-emerald-200">
                  No issues found.
                </div>
              )
            ) : (
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 text-slate-400">
                Run validation to see backend feedback here.
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
