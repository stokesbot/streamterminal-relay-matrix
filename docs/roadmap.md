# Roadmap

## Phase 0 — Concept validation

Status: completed outside this repo.

Completed learnings from the live test stack:
- MediaMTX works well as RTMP ingest layer
- `stream-failover-relay` can switch between primary and backup streams
- matching encoder profiles are critical for clean failover
- the relay benefits from systemd auto-restart protection
- manual operations are workable but not operator-friendly

---

## Phase 1 — Planning and project foundation

Goal:
- define product direction and MVP boundary
- initialize repo and docs
- choose stack and local development workflow

Deliverables:
- README
- product vision
- architecture
- MVP plan
- roadmap
- initial repo structure

---

## Phase 2 — Local developer platform

Goal:
- make it easy to run the app locally

Deliverables:
- app skeletons (`apps/api`, `apps/web`)
- local run instructions
- `.env.example`
- docker-compose or equivalent local runtime simulation decision
- sample fixture configs

---

## Phase 3 — Config control plane

Goal:
- build the configuration lifecycle

Deliverables:
- config schema and persistence
- draft/live revision model
- validation pipeline
- apply/rollback mechanics
- generated runtime file templates

---

## Phase 4 — Monitoring and observability

Goal:
- make runtime state visible to operators

Deliverables:
- dashboard summary
- input/output status panels
- active source indicator
- logs page
- failover event timeline
- service status and host basics

---

## Phase 5 — Runtime integration hardening

Goal:
- safely manage real services and real configs

Deliverables:
- service control wrappers
- atomic config writes
- dependency checks
- safer error handling
- rollback verification

---

## Phase 6 — Staging validation

Goal:
- run the control plane against a realistic staging stack

Deliverables:
- synthetic stream test harness
- real RTMP scenario validation
- failover test report
- recovery-path tests

---

## Phase 7 — Production rollout

Goal:
- deploy to the target server once stable

Deliverables:
- production deployment notes
- backup/restore steps
- operational runbook
- migration checklist from manual setup

---

## Later roadmap ideas

### Multi-channel
- multiple pipelines in one UI
- grouped service management
- per-channel event history

### Richer protocol support
- RTMP + SRT mixed workflows
- listener/caller mode controls
- destination presets

### Smart validation
- codec/fps/resolution compatibility checks
- risky profile detection
- preflight warnings before apply

### Preview and diagnostics
- HLS or WebRTC preview if practical
- richer metrics
- probe history graphs

### Notifications
- Telegram alerts
- webhooks
- email notifications

### Recording / extra MediaMTX features
- optional recording
- path hooks
- future auth integrations

---

## Recommended current path

1. finish planning docs
2. scaffold local project
3. build config UI and backend schema
4. add monitoring stubs
5. integrate runtime control
6. test locally
7. only then move to staging/production server
