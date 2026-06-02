# StreamTerminal Relay Matrix

Control-plane application for managing a failover streaming stack built around MediaMTX and `stream-failover-relay`.

## Purpose

This project aims to provide a proper operator-facing layer on top of proven streaming components instead of building a custom streaming server from scratch.

The target outcome is a local/hosted appliance that can:

- configure primary and backup inputs
- configure output endpoints
- manage RTMP / SRT and related ingest options
- validate stream compatibility
- monitor process and connection health
- surface failover events and operational logs
- safely apply and roll back runtime configuration

## Core idea

- **MediaMTX** handles ingest/server-side streaming protocols.
- **stream-failover-relay** handles active/backup switching and output publishing.
- **This app** provides configuration, validation, monitoring, event history, and safe operations.

## Current stack

- **Frontend:** Next.js
- **Backend:** FastAPI
- **State (prototype):** JSON draft config on disk
- **Target runtime:** MediaMTX + stream-failover-relay + systemd

## Repository layout

```text
apps/
  api/    FastAPI control API
  web/    Next.js operator UI
docs/     Product and architecture docs
ops/      Reserved for runtime templates / scripts / service files
```

## Quick start

### Backend

```bash
cd apps/api
cp .env.example .env
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

### Frontend

```bash
cd apps/web
cp .env.example .env.local
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open:

```text
http://127.0.0.1:3000
```

## Current prototype features

- dashboard shell
- configuration page
- diagnostics page with artifact previews, host tool probes, and systemd unit state
- deployment planning page with profile selection, staged-vs-target mapping, command previews, and rollout notes
- deployment audit view with file checksums, changed/new/unchanged summaries, and latest-bundle comparison
- saved target profile creation stored outside git-tracked repo files
- safe deploy execution page actions for preview mode and local bundle generation
- backend draft config load/save
- backend config validation endpoint
- backend apply / rollback endpoints
- generated MediaMTX and relay runtime artifacts
- generated systemd unit templates for both runtime services
- placeholder-only env-file template generation with masked current URL previews
- staged local install layout under `apps/api/data/runtime/install-root/`
- deployment profile API, saved-target API, and staged-to-target rollout plan endpoint
- deployment audit endpoint backed by per-bundle manifests and sha256 comparison
- safe deploy bundle execution endpoint that writes reviewed artifacts under `apps/api/data/runtime/deploy-bundles/`
- service-control API with dry-run or execute modes for known runtime services
- log inspection API via `journalctl`
- UI controls for apply / stage-install / service actions / log fetch
- diagnostics endpoint with template previews and host binary probing
- runtime status endpoint backed by real local command availability checks
- dark operator UI scaffold

## Documentation

See:

- `docs/product-vision.md`
- `docs/architecture.md`
- `docs/mvp-plan.md`
- `docs/roadmap.md`

## Proposed MVP

Start with a **single-channel failover appliance**:

- Input A
- Input B
- Output
- Health dashboard
- Event log
- Config validation
- Safe apply / rollback

Design the data model so multi-channel support can be added later.

## Status

Prototype scaffold complete. Runtime integration, service controls, diagnostics, deployment planning, safe local bundle generation, deployment audits, and saved target profiles are now wired. Real remote deployment execution should remain manual until host-specific auth, secrets, and rollback policies are finalized.
