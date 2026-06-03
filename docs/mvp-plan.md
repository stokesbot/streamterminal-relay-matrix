# MVP Plan

## MVP goal

Build a local-first operator console for a single failover pipeline:

- primary input
- backup input
- one output
- runtime status
- recent failover/health events
- safe config apply and rollback

---

## Scope

## In scope for MVP

### Configuration
- primary input URL
- backup input URL
- output URL
- protocol selection and basic endpoint options, including RTMP/SRT and caller/listener where applicable
- simple runtime options (enabled/disabled, auto-restart)

### Runtime control
- start services
- stop services
- restart services
- apply config
- rollback last applied config

### Monitoring
- service up/down state
- input availability state
- output connected/disconnected state
- active source indicator
- recent logs
- recent failover events

### Validation
- URL/protocol validation
- required field validation
- SRT-specific validation for mode, latency, and encryption inputs when SRT is selected
- basic compatibility warnings model
- pre-apply safety checks

### Documentation
- setup instructions
- architecture notes
- config lifecycle notes

---

## Explicitly out of scope for MVP

- multi-channel UI
- user accounts/roles
- distributed deployment
- deep bitrate analytics
- built-in transcoding pipeline
- full alerting integrations
- multi-tenant management
- complex auth system
- full MediaMTX feature surface

---

## MVP screens

## 1. Dashboard
Widgets:
- overall runtime state
- active source
- primary input health
- backup input health
- output health
- service status cards
- recent events

## 2. Configuration screen
Sections:
- channel identity
- primary input
- backup input
- output settings
- runtime toggles
- validation panel
- apply / rollback controls

## 3. Logs & events screen
Sections:
- recent failover events
- MediaMTX logs
- relay logs
- filtering by severity/component

## 4. Diagnostics screen
Sections:
- generated config preview
- service status detail
- dependency versions
- probe test results

---

## Backend MVP endpoints

## Config
- `GET /api/config`
- `PUT /api/config/draft`
- `POST /api/config/validate`
- `POST /api/config/apply`
- `POST /api/config/rollback`

## Runtime
- `GET /api/runtime/status`
- `POST /api/runtime/start`
- `POST /api/runtime/stop`
- `POST /api/runtime/restart`

## Monitoring
- `GET /api/health/summary`
- `GET /api/events`
- `GET /api/logs`
- `GET /api/diagnostics`

---

## Minimal data model

### channel_config
- id
- name
- enabled
- primary_input_url
- backup_input_url
- output_url
- input_protocol
- output_protocol
- auto_restart
- mediamtx_enabled
- relay_enabled
- created_at
- updated_at

### config_revisions
- id
- version
- payload_json
- status
- created_at
- notes

### runtime_events
- id
- type
- severity
- source
- message
- metadata_json
- created_at

---

## Acceptance criteria

The MVP is done when:

1. a user can open the UI locally
2. a user can save a draft failover configuration
3. a user can validate and apply that config
4. the backend generates the needed runtime files
5. the backend can restart the controlled services
6. the UI shows whether primary, backup, and output are healthy
7. the UI shows which source is active
8. recent logs can be viewed without shell access
9. a failed apply can be rolled back

---

## Suggested implementation phases

## Phase 1 — Planning and repo setup
- docs
- directory structure
- stack decision
- local dev workflow

## Phase 2 — Backend skeleton
- FastAPI app
- config schema
- SQLite setup
- health/status stubs

## Phase 3 — Frontend skeleton
- Next.js app shell
- dashboard layout
- config page layout
- API wiring

## Phase 4 — Runtime integration
- file/template generation
- service control hooks
- draft/apply/rollback flow

## Phase 5 — Monitoring integration
- log readers
- status synthesis
- event timeline

## Phase 6 — Local end-to-end validation
- synthetic feeds
- test configs
- happy path apply
- failover test

---

## Recommended first engineering slice

If we start coding immediately, the first useful slice should be:

1. backend config schema
2. save/load draft config
3. frontend config form
4. validate action
5. dashboard stub with mocked health data

That gets us a visible product quickly without touching live service control yet.
