# Architecture

## Architecture summary

The system should be built as a **control plane over an external streaming runtime**.

### Runtime components
- MediaMTX
- stream-failover-relay
- systemd services
- optional FFmpeg helper processes

### Product components
- Web UI
- API/backend service
- config/state store
- runtime adapter layer
- monitoring/event collector

---

## High-level architecture

```text
+--------------------+
|      Web UI        |
| config / status    |
| logs / events      |
+---------+----------+
          |
          | HTTP / WS
          v
+--------------------+
|   Control API      |
| validation         |
| config lifecycle   |
| process control    |
| health synthesis   |
+----+----+----+-----+
     |    |    |
     |    |    +----------------------+
     |    |                           |
     |    v                           v
     |  SQLite / files          metrics / log parser
     |
     v
+--------------------+
| Runtime adapter    |
| render configs     |
| manage services    |
| probe endpoints    |
+----+-----------+---+
     |           |
     |           |
     v           v
+---------+   +------------------------+
|MediaMTX |   | stream-failover-relay  |
+---------+   +------------------------+
     |                    |
     | ingest             | output publish
     v                    v
 primary / backup     destination endpoint
```

---

## Recommended stack

## Frontend
- Next.js
- TypeScript
- Tailwind
- simple component system (shadcn/ui if desired later)

## Backend
Preferred:
- FastAPI
- Python 3.12+
- Pydantic for schema validation

Why FastAPI:
- strong typed config models
- easy system integration on Linux
- good fit for process control and file rendering
- easy to expose health/status endpoints

## Storage
- SQLite for durable app state
- YAML or generated service/config files for runtime
- append-only event log table for failover history

## Runtime integration
- systemd service control via subprocess
- templates for generated config files
- local probes for RTMP/SRT availability where possible
- log parsing from service logs or dedicated log files

---

## Proposed repository layout

```text
apps/
  api/
  web/
docs/
ops/
  systemd/
  templates/
  scripts/
packages/
  shared/          # optional later for shared types/contracts
fixtures/
  configs/
  streams/
```

### Early practical variant

For the first iteration, this simpler structure is enough:

```text
apps/
  api/
  web/
docs/
ops/
```

---

## Core backend modules

## 1. Configuration domain
Responsible for:
- channel config schema
- protocol-specific validation
- compatibility rules
- persistence
- draft/live versioning

### Entities

#### ChannelConfig
- id
- name
- enabled
- primary_input
- backup_input
- output
- mediamtx_enabled
- relay_enabled
- auto_restart
- created_at
- updated_at

#### StreamEndpoint
- protocol (`rtmp`, `srt`, `rtsp`, etc.)
- url
- mode (`push`, `pull`, `listener`, `caller`) where relevant
- label
- enabled

#### RuntimeProfile
- expected video codec
- expected audio codec
- expected fps
- expected resolution
- expected keyframe interval
- optional normalization policy

#### ConfigRevision
- id
- channel_id
- version
- status (`draft`, `validated`, `applied`, `rolled_back`)
- payload
- created_at
- created_by

## 2. Runtime adapter
Responsible for:
- rendering MediaMTX config
- rendering relay/systemd launch config
- writing files atomically
- restarting/reloading services
- checking service health
- collecting process status

### Adapter responsibilities
- `validate_runtime_dependencies()`
- `render_mediamtx_config()`
- `render_relay_command()`
- `apply_revision()`
- `rollback_revision()`
- `get_service_status()`

## 3. Monitoring service
Responsible for:
- active input detection
- input/output health checks
- event collection
- recent logs view
- host-level stats

### Monitoring outputs
- current active source
- last successful output publish time
- recent disconnects/reconnects
- bitrate/fps/resolution when available
- CPU, RAM, disk, network basics

## 4. API layer
Responsibilities:
- expose config CRUD
- validate/apply endpoints
- status endpoints
- event/log endpoints
- control actions (`start`, `stop`, `restart`)

---

## UI architecture

## Main views

### 1. Dashboard
Shows:
- runtime overall health
- primary input state
- backup input state
- output state
- active source
- recent failover events
- quick actions

### 2. Configuration page
Sections:
- primary input
- backup input
- output endpoint
- protocol options
- runtime toggles
- validation results
- apply / rollback actions

### 3. Logs & events page
Shows:
- failover timeline
- process errors
- filtered logs by component
- last restart / last outage markers

### 4. Diagnostics page
Shows:
- service status
- rendered config preview
- runtime versions
- probe results
- compatibility warnings

---

## Control flow

## Save draft
1. user edits config in UI
2. backend validates schema
3. backend stores draft revision
4. UI shows validation state

## Apply config
1. user clicks Apply
2. backend validates draft
3. backend writes generated runtime files
4. backend backs up previous live config
5. backend restarts/reloads services
6. backend performs post-apply health checks
7. backend marks revision as applied or failed
8. UI shows result and rollback option

## Failover event handling
1. runtime logs or probes indicate source switch
2. monitoring service records event
3. dashboard updates active source
4. event timeline updates
5. optional notifier emits alert later

---

## Deployment model

## Local development
- app runs locally
- runtime components may run locally in Docker or directly
- synthetic streams used for testing

## Server deployment
- app runs on same machine as runtime or separately
- backend needs permission to manage service files and systemd
- service integration should be explicit and auditable

### Recommendation
For v1, deploy the control plane on the **same host** as the runtime stack when moving to production, because local process and log access are simpler.

---

## Security considerations

- secrets should not be hard-coded in source
- output keys/stream keys must be masked in UI where possible
- config writes should be versioned and auditable
- dangerous actions should require explicit confirmation
- avoid arbitrary command execution from UI
- backend should whitelist exactly which service files and commands it manages

---

## Open decisions

1. FastAPI + Next.js vs full Next.js backend
2. whether monitoring uses only logs at first or also metrics exporters
3. whether local dev uses Docker Compose for runtime simulation
4. whether to support only single channel in the UI initially or expose future channel model immediately

## Recommendation

Use:
- **Next.js frontend**
- **FastAPI backend**
- **SQLite state store**
- **systemd + generated templates**
- **single-channel MVP with multi-channel-ready schema**
