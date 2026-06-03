# StreamTerminal Relay Matrix — Operator Runbook

This runbook covers the day-to-day operations of a running StreamTerminal
Relay Matrix. It is written for an operator with shell access to the host
running the relay manager.

> **Deployment model.** Everything in this runbook is local-only. The
> relay manager, the API, the UI, and the relay itself all run on the
> same Linux host. There is no SSH/rsync/VPS step.

> **Where things live.**
>
> | Path | Purpose |
> | --- | --- |
> | `/etc/streamterminal-relay-matrix/` | Config dir (managed by `apply`) |
> | `/etc/streamterminal-relay-matrix/mediamtx.yml` | Generated mediamtx config |
> | `/etc/streamterminal-relay-matrix/streamterminal-relay.env` | Live env with secrets (NEVER auto-edited) |
> | `/etc/streamterminal-relay-matrix/streamterminal-relay.env.example` | Generated template (no secrets) |
> | `/usr/local/bin/relay-command.sh` | Relay entry script |
> | `/usr/local/bin/mediamtx` | mediamtx binary |
> | `/usr/local/bin/stream-failover-relay` | Relay binary |
> | `/etc/systemd/system/mediamtx.service` | mediamtx unit (hardened) |
> | `/etc/systemd/system/stream-failover-relay.service` | Relay unit (hardened) |
> | `apps/api/data/runtime/deploy-bundles/` | Local install bundle history |
> | `apps/api/data/runtime/host-snapshots/` | Pre-apply host file snapshots |
> | `apps/api/data/runtime/install-root/` | Staging dir used by `apply` |

---

## Quick links

- **UI**: `http://127.0.0.1:3000`
- **API**: `http://127.0.0.1:8000/api/...` (see [API endpoints](#api-endpoints))
- **Smoke loop**: `http://127.0.0.1:3000/` → "Live smoke" panel
- **Deploy page**: `http://127.0.0.1:3000/deploy`
- **Off-band restore CLI**: `uv run python apps/api/scripts/host_restore_snapshot.py`

---

## 1. First-boot checks

After a fresh install, run these in order:

```bash
# 1. Preflight — read-only, no host changes
curl -sS http://127.0.0.1:8000/api/deploy/preflight?profile_id=local-system | jq

# 2. Check both services are active and running
systemctl is-active mediamtx
systemctl is-active stream-failover-relay
systemctl show mediamtx.service --property=ActiveState,SubState,UnitFileState

# 3. Confirm mediamtx is actually listening on the RTMP port
ss -ltn | grep ':1935'

# 4. Run a smoke probe
curl -sS http://127.0.0.1:8000/api/runtime/smoke | jq

# 5. If the relay env file is missing, seed it from the example
test -f /etc/streamterminal-relay-matrix/streamterminal-relay.env \
  || sudo cp /etc/streamterminal-relay-matrix/streamterminal-relay.env.example \
       /etc/streamterminal-relay-matrix/streamterminal-relay.env
sudo chmod 600 /etc/streamterminal-relay-matrix/streamterminal-relay.env
# ...then fill in STM_PRIMARY_INPUT_URL / STM_BACKUP_INPUT_URL / STM_OUTPUT_URL
sudo systemctl restart stream-failover-relay.service
```

> If `apply` reports `Live relay env readiness` as **No**, edit the
> live env file by hand and re-run the apply. The apply will never
> overwrite a live env file; it only seeds it from the example when
> the file is missing.

---

## 2. After a reboot

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mediamtx.service
sudo systemctl enable --now stream-failover-relay.service

# Quick health check
curl -sS http://127.0.0.1:8000/api/runtime/smoke | jq '.summary'
```

The unit files are hardened:
- `After=network-online.target` + `Wants=network-online.target`
- `Restart=always` / `RestartSec=2`
- `LimitNOFILE=65536` on both
- `MemoryMax=512M` on the relay
- `StandardOutput=journal` / `StandardError=journal`

---

## 3. After a config change

You only need three steps:

1. Edit the draft in the UI at `/config` (or POST to `/api/config` directly).
2. Click **Validate draft** to catch obvious problems.
3. Click **Apply draft** to:
   - snapshot the current `/etc` state (auto-recoverable)
   - write the new files
   - reload systemd, enable + start the services
   - verify the RTMP listener
   - return a structured step list

```bash
# Equivalent CLI flow (rare — the UI is the supported path)
curl -sS -X POST http://127.0.0.1:8000/api/config/apply
curl -sS -X POST http://127.0.0.1:8000/api/runtime/smoke
```

---

## 4. When a publisher can't connect

1. **Open `/`** → "Live smoke" panel. Look at the four red/green checks.
2. If `mediamtx rtmp listener` is **fail**:
   ```bash
   ss -ltn | grep ':1935'         # should show :1935
   journalctl -u mediamtx --no-pager -n 100
   ```
3. If `mediamtx service` is **fail** but the listener is up:
   ```bash
   systemctl show mediamtx.service --property=ActiveState,SubState,UnitFileState
   sudo systemctl restart mediamtx.service
   ```
4. If `primary input reachable` or `backup input reachable` is **fail**:
   - the publisher's URL is unreachable from this host
   - check firewall, route, upstream RTMP endpoint
5. If `output destination reachable` is **fail**:
   - the IBM VS Ustream URL is unreachable
   - the relay will keep retrying; no operator action required unless the
     URL has changed (then update `/etc/streamterminal-relay-matrix/streamterminal-relay.env` and restart the relay)

---

## 5. When the relay crashes

1. **Open `/`** → "Live smoke" panel. If `stream-failover-relay service` is
   **fail** with `NRestarts >= 3` the relay is in a crash loop.
2. Check the journal:
   ```bash
   journalctl -u stream-failover-relay --no-pager -n 200
   ```
3. If the crash is environmental (bad upstream URL, missing binary):
   - fix the upstream URL in `/etc/streamterminal-relay-matrix/streamterminal-relay.env`
   - `sudo systemctl restart stream-failover-relay.service`
4. If the relay binary itself is broken:
   - `sudo cp /usr/local/bin/stream-failover-relay{.broken,}` (or use the bundle)
   - reinstall via the UI by clicking **Apply draft** again

The relay is configured to restart on failure with `RestartSec=2`.

---

## 6. Rolling back to a known-good state

The pre-apply host snapshot subsystem captures the on-host `/etc` files
before every apply. Restoring a snapshot is two clicks or one CLI command.

### From the UI

1. Open `/deploy`.
2. Scroll to **Local host snapshots**.
3. Click **Restore** on the snapshot you want.
4. Confirm the dialog.

### From the CLI (when the API is down)

```bash
cd /opt/stokesbot/streamterminal-relay-matrix
RUNTIME_DIR=apps/api/data/runtime \
  uv run python apps/api/scripts/host_restore_snapshot.py list
RUNTIME_DIR=apps/api/data/runtime \
  uv run python apps/api/scripts/host_restore_snapshot.py restore <snapshot_id> --dry-run
RUNTIME_DIR=apps/api/data/runtime \
  uv run python apps/api/scripts/host_restore_snapshot.py restore <snapshot_id>
```

The CLI writes directly to the host (using `install -m` semantics), so
double-check the snapshot id with `list` / `show` first.

### From the API

```bash
# Dry-run preview (no writes)
curl -sS -X POST http://127.0.0.1:8000/api/deploy/restore-snapshot \
  -H 'Content-Type: application/json' \
  -d '{"snapshot_id": "<id>", "execute": false}'

# Real restore
curl -sS -X POST http://127.0.0.1:8000/api/deploy/restore-snapshot \
  -H 'Content-Type: application/json' \
  -d '{"snapshot_id": "<id>", "execute": true}'
```

After any rollback, run a smoke check:

```bash
curl -sS http://127.0.0.1:8000/api/runtime/smoke | jq '.summary'
```

---

## 7. Backing out a bad bundle

A bundle is the staged `rootfs/` tree that was used to write the host.
`/api/deploy/audit` compares the staged files against the latest apply
bundle, and `/api/deploy/execute?action=rollback` re-applies the
previous bundle.

```bash
# Audit the current host against the latest apply bundle
curl -sS 'http://127.0.0.1:8000/api/deploy/audit?profile_id=local-system' | jq

# Roll back to the previous applied bundle
curl -sS -X POST http://127.0.0.1:8000/api/deploy/execute \
  -H 'Content-Type: application/json' \
  -d '{"profile_id": "local-system", "execute": true, "action": "rollback"}'
```

> **Note:** `rollback` re-applies the **previous** apply bundle. It does
> **not** roll back to the snapshot. If the previous bundle itself was
> bad, use a host snapshot instead (see section 6).

---

## 8. Manually re-enabling the live env file

The apply path **never** overwrites a live env file. The only way the
file gets recreated is if it is missing. To rotate it after a credential
change:

```bash
# 1. Make a backup
sudo cp /etc/streamterminal-relay-matrix/streamterminal-relay.env{,.bak}

# 2. Edit the new values
sudoedit /etc/streamterminal-relay-matrix/streamterminal-relay.env

# 3. Lock it down
sudo chmod 600 /etc/streamterminal-relay-matrix/streamterminal-relay.env

# 4. Restart the relay so it picks up the new env
sudo systemctl restart stream-failover-relay.service

# 5. Verify
curl -sS http://127.0.0.1:8000/api/runtime/smoke | jq '.checks[] | select(.name | contains("input") or contains("output"))'
```

The env file format is:

```bash
STM_PRIMARY_INPUT_URL=rtmp://primary.example.com/live/main
STM_BACKUP_INPUT_URL=rtmp://backup.example.com/live/backup
STM_OUTPUT_URL=rtmp://ingest.example.com/live/output
```

> The relay refuses to start cleanly if any of these are missing or
> still contain the literal `REPLACE_WITH_` / `example.invalid` /
> `placeholder` markers from the example template.

---

## 9. Disk hygiene

`apps/api/data/runtime/deploy-bundles/` and `apps/api/data/runtime/install-root/`
grow on every apply. Rotation is bounded by two env vars:

| Env var | Default | Purpose |
| --- | --- | --- |
| `STM_BUNDLE_KEEP_APPLY` | 20 | Number of most recent apply bundles to keep |
| `STM_BUNDLE_KEEP_STAGE` | 5 | Number of most recent staging dirs to keep |

The most recent apply bundle is **always** kept, even with
`STM_BUNDLE_KEEP_APPLY=0`, so you always have at least one rollback source.

```bash
# Inventory
curl -sS http://127.0.0.1:8000/api/runtime/bundles | jq

# Prune (with confirm)
curl -sS -X POST http://127.0.0.1:8000/api/runtime/prune-bundles \
  -H 'Content-Type: application/json' -d '{}'

# Or from the UI: /deploy → "Bundle inventory and rotation" → "Prune old bundles"
```

---

## 10. API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness check |
| GET | `/api/runtime/status` | Pipeline state, services, recent events |
| GET | `/api/runtime/smoke` | 6-check live health probe |
| GET | `/api/runtime/bundles` | Inventory of bundles + staging dirs |
| POST | `/api/runtime/prune-bundles` | Prune bundles (bodies: `{keep_apply?, keep_stage?, execute?}`) |
| GET | `/api/config` | Current draft config |
| POST | `/api/config/apply` | Apply current draft as a new revision |
| GET | `/api/diagnostics` | Runtime inspection |
| GET | `/api/deploy/profiles` | List deploy profiles (only `local-system`) |
| GET | `/api/deploy/preflight` | Read-only preflight checks |
| GET | `/api/deploy/plan` | Generated plan for a profile |
| GET | `/api/deploy/audit` | Compare host files against the latest bundle |
| GET | `/api/deploy/host-snapshots` | List captured pre-apply host snapshots |
| POST | `/api/deploy/restore-snapshot` | Restore a snapshot (bodies: `{snapshot_id, execute}`) |
| POST | `/api/deploy/execute` | `preview` / `bundle` / `apply` / `rollback` |
| POST | `/api/services/{name}/action` | `start` / `stop` / `restart` / `daemon-reload` / `enable` / `disable` |
| GET | `/api/services/{name}/logs` | Last N journal lines |

---

## 11. Troubleshooting matrix

| Symptom | First check | Second check | Likely cause |
| --- | --- | --- | --- |
| Smoke shows `mediamtx service` fail | `systemctl show mediamtx.service --property=ActiveState,SubState` | `journalctl -u mediamtx -n 100` | Binary missing or crashed during startup |
| Smoke shows `mediamtx rtmp listener` fail but service is active | `ss -ltn | grep 1935` | `journalctl -u mediamtx -n 100` | Port 1935 already in use, or bind to wrong interface |
| Smoke shows `stream-failover-relay service` fail with `NRestarts > 0` | `journalctl -u stream-failover-relay -n 200` | `cat /etc/streamterminal-relay-matrix/streamterminal-relay.env` | Bad upstream URL, missing env vars, or binary crash |
| Smoke shows `primary/backup/output reachable` fail | `curl -v <url>` from the host | `nslookup <host>` | Firewall, DNS, or upstream RTMP endpoint down |
| Apply reports `Live relay env readiness: no` | Check `/etc/streamterminal-relay-matrix/streamterminal-relay.env` | Re-run apply after fixing | Live env still has placeholder values |
| Apply reports `Snapshot host files before apply` fail | Check disk space on the runtime dir | Check `STM_RUNTIME_DIR` permissions | Runtime dir full or read-only |
| Restore snapshot fails with `snapshot not found` | `curl -sS http://127.0.0.1:8000/api/deploy/host-snapshots` | Reread the `id` exactly | Wrong id, or snapshot was pruned (not yet implemented) |
| UI shows `404` on `/api/runtime/smoke` | `curl -sS http://127.0.0.1:8000/api/runtime/smoke` | Restart the API | API version too old; redeploy the latest `main` |

---

## 12. Recovering from a corrupt data dir

The runtime dir (`apps/api/data/runtime/`) is the only stateful dir the
manager keeps. If it gets corrupted:

1. Stop the API.
2. Back up the current state: `mv apps/api/data/runtime apps/api/data/runtime.broken`
3. Re-apply: in the UI on a fresh install, click **Apply draft**. A
   brand-new runtime dir is created.
4. The new install is the most recent bundle. To restore the previous
   host state, use the host snapshot from the broken runtime:
   ```bash
   # Copy the most recent snapshot out of the broken runtime
   cp -r apps/api/data/runtime.broken/host-snapshots /tmp/host-snapshots
   # Then either point the API at it, or restore manually with the CLI
   RUNTIME_DIR=apps/api/data/runtime \
     uv run python apps/api/scripts/host_restore_snapshot.py list
   RUNTIME_DIR=apps/api/data/runtime \
     uv run python apps/api/scripts/host_restore_snapshot.py restore <id>
   ```
5. Restart the API.

---

## 13. Smoke tests and CI

The repo runs three CI jobs on every push and PR:

- **Backend tests** — `apps/api` unittests (24 tests)
- **Frontend lint + build** — Next.js + ESLint
- **End-to-end tests** — Playwright with a real backend in a sandbox

If a job fails on your PR, the diff between the failing run and the
last green run is the source of truth. The e2e harness in
`apps/web/tests/relayMatrixServer.ts` runs the real FastAPI app in a
temp dir with a fake `sudo` / `systemctl` / `mediamtx` / `stream-failover-relay`
/ `ss` on a temp `PATH`, so it never mutates the host.

---

## 14. Where to get help

- The architecture overview is in `docs/architecture.md`.
- The product vision is in `docs/product-vision.md`.
- The MVP plan and roadmap are in `docs/mvp-plan.md` and `docs/roadmap.md`.
- The deploy page UI also acts as live documentation — every section
  is annotated with what it does and where its data comes from.
