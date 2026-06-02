import { spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, sep } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const FAKE_SUDO = `#!/usr/bin/env python3
import os
import subprocess
import sys

args = sys.argv[1:]
if args[:1] == ['-n']:
    args = args[1:]
if not args:
    sys.exit(0)
raise SystemExit(subprocess.run(args, env=os.environ.copy()).returncode)
`;

const FAKE_SYSTEMCTL = `#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ['FAKE_SYSTEMCTL_STATE'])
state_path.parent.mkdir(parents=True, exist_ok=True)
state = json.loads(state_path.read_text()) if state_path.exists() else {}
args = sys.argv[1:]


def save():
    state_path.write_text(json.dumps(state))


def ensure(unit):
    state.setdefault(unit, {'ActiveState': 'inactive', 'SubState': 'dead', 'UnitFileState': 'disabled', 'ExecMainStatus': '0', 'NRestarts': '0'})


def relay_env_ready():
    env_path = Path(os.environ['FAKE_RELAY_ENV'])
    if not env_path.exists():
        return False
    payload = env_path.read_text()
    required = ['STM_PRIMARY_INPUT_URL=', 'STM_BACKUP_INPUT_URL=', 'STM_OUTPUT_URL=']
    if not all(item in payload for item in required):
        return False
    return 'REPLACE_WITH_' not in payload and 'example.invalid' not in payload and 'placeholder' not in payload.lower()


if not args:
    raise SystemExit(1)

if args[0] == '--version':
    print('systemd 999 (fake)')
    raise SystemExit(0)

if args[0] == 'is-system-running':
    print('running')
    raise SystemExit(0)

if args[0] == 'daemon-reload':
    print('reloaded')
    raise SystemExit(0)

if args[0] in {'enable', 'disable'}:
    action = args[0]
    units = [arg for arg in args[1:] if not arg.startswith('-')]
    for unit in units:
        ensure(unit)
        if action == 'enable':
            if unit == 'stream-failover-relay.service' and not relay_env_ready():
                state[unit].update({'ActiveState': 'activating', 'SubState': 'auto-restart', 'UnitFileState': 'enabled', 'ExecMainStatus': '1', 'NRestarts': '2'})
            else:
                state[unit].update({'ActiveState': 'active', 'SubState': 'running', 'UnitFileState': 'enabled', 'ExecMainStatus': '0', 'NRestarts': '0'})
        else:
            state[unit].update({'ActiveState': 'inactive', 'SubState': 'dead', 'UnitFileState': 'disabled', 'ExecMainStatus': '0', 'NRestarts': '0'})
    save()
    print(action)
    raise SystemExit(0)

if args[0] == 'show':
    units = []
    for arg in args[1:]:
        if arg.startswith('--'):
            continue
        units.append(arg)
    lines = []
    for unit in units:
        ensure(unit)
        for key in ['ActiveState', 'UnitFileState', 'SubState', 'ExecMainStatus', 'NRestarts']:
            lines.append(f'{key}={state[unit][key]}')
    print('\\n'.join(lines))
    raise SystemExit(0)

if args[0] == 'status':
    units = [arg for arg in args[1:] if not arg.startswith('-')]
    for unit in units:
        ensure(unit)
        print(f"{unit} {state[unit]['ActiveState']}")
    raise SystemExit(0)

raise SystemExit(0)
`;

const FAKE_TOOL = `#!/usr/bin/env bash
echo fake-$0
exit 0
`;

const VALID_RELAY_ENV_LINES = [
  "STM_PRIMARY_INPUT_URL=rtmp://localhost:1935/live/main",
  "STM_BACKUP_INPUT_URL=rtmp://localhost:1935/live/backup",
  "STM_OUTPUT_URL=rtmp://localhost:1935/live/output",
];

export type RelayMatrixServerOptions = {
  apiPort: number;
};

export type RelayMatrixServerHandle = {
  apiBaseUrl: string;
  dataDir: string;
  fakebinDir: string;
  liveEnvPath: string;
  writeValidRelayEnv(): void;
  stop(): Promise<void>;
};

function ensureExecutable(path: string, body: string): void {
  writeFileSync(path, body, { mode: 0o755 });
}

async function waitForHealth(apiBaseUrl: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = null;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${apiBaseUrl}/api/health`);
      if (res.ok) {
        return;
      }
      lastError = new Error(`status ${res.status}`);
    } catch (error) {
      lastError = error;
    }
    await delay(150);
  }
  throw new Error(`API at ${apiBaseUrl}/api/health did not become healthy in ${timeoutMs}ms: ${String(lastError)}`);
}

function repoRootFromTests(): string {
  return join(__dirname, "..", "..", "..");
}

export async function startRelayMatrixServer(options: RelayMatrixServerOptions): Promise<RelayMatrixServerHandle> {
  const repoRoot = repoRootFromTests();
  const workdir = mkdtempSync(`${tmpdir()}${sep}relay-matrix-e2e-`);
  const fakebinDir = join(workdir, "fakebin");
  const dataDir = join(workdir, "data");
  const hostRoot = join(workdir, "host");
  const statePath = join(workdir, "systemctl-state.json");
  const liveEnvPath = join(hostRoot, "etc", "streamterminal-relay-matrix", "streamterminal-relay.env");

  mkdirSync(fakebinDir, { recursive: true });
  mkdirSync(dataDir, { recursive: true });
  mkdirSync(join(hostRoot, "etc", "streamterminal-relay-matrix"), { recursive: true });

  ensureExecutable(join(fakebinDir, "sudo"), FAKE_SUDO);
  ensureExecutable(join(fakebinDir, "systemctl"), FAKE_SYSTEMCTL);
  ensureExecutable(join(fakebinDir, "mediamtx"), FAKE_TOOL);
  ensureExecutable(join(fakebinDir, "stream-failover-relay"), FAKE_TOOL);

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PATH: `${fakebinDir}${pathDelim(process.env.PATH)}`,
    FAKE_SYSTEMCTL_STATE: statePath,
    FAKE_RELAY_ENV: liveEnvPath,
    STM_TEST_HOST_ROOT: hostRoot,
    ALLOWED_ORIGINS: JSON.stringify([`http://127.0.0.1:${process.env.E2E_WEB_PORT ?? "3001"}`]),
  };

  const apiBaseUrl = `http://127.0.0.1:${options.apiPort}`;
  const apiProcess: ChildProcess = spawn(
    "uv",
    [
      "run",
      "--directory",
      join(repoRoot, "apps", "api"),
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(options.apiPort),
    ],
    {
      cwd: repoRoot,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  let stopped = false;
  let stopPromise: Promise<void> = Promise.resolve();
  const stop = async (): Promise<void> => {
    if (stopped) {
      return stopPromise;
    }
    stopped = true;
    stopPromise = new Promise<void>((resolve) => {
      const proc = apiProcess;
      if (proc.exitCode !== null || proc.signalCode !== null) {
        resolve();
        return;
      }
      proc.once("exit", () => resolve());
      try {
        proc.kill("SIGTERM");
      } catch {
        resolve();
      }
    });
    try {
      await Promise.race([stopPromise, delay(5_000)]);
    } finally {
      try {
        if (apiProcess.exitCode === null && apiProcess.signalCode === null) {
          apiProcess.kill("SIGKILL");
        }
      } catch {
        // already gone
      }
    }
    try {
      rmSync(workdir, { recursive: true, force: true });
    } catch {
      // best-effort cleanup
    }
  };

  const handle: RelayMatrixServerHandle = {
    apiBaseUrl,
    dataDir,
    fakebinDir,
    liveEnvPath,
    writeValidRelayEnv(): void {
      writeFileSync(liveEnvPath, `${VALID_RELAY_ENV_LINES.join("\n")}\n`, { mode: 0o644 });
    },
    stop,
  };

  apiProcess.once("error", (error) => {
    if (!stopped) {
      stopped = true;
    }
    throw error;
  });

  apiProcess.stdout?.on("data", () => {
    // noop; tests assert against HTTP responses, not logs
  });
  apiProcess.stderr?.on("data", () => {
    // noop
  });

  try {
    await waitForHealth(apiBaseUrl, 30_000);
  } catch (error) {
    await stop();
    throw error;
  }

  return handle;
}

function pathDelim(input: string | undefined): string {
  if (!input) {
    return "";
  }
  return process.platform === "win32" ? ";" : `:${input}`;
}
