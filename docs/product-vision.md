# Product Vision

## Working title

StreamTerminal Relay Matrix

## Problem

The current failover stack works technically, but operating it is too manual:

- inputs and outputs are configured by editing files
- service restarts are manual or shell-driven
- logs and state are scattered across the host
- there is no single operator dashboard
- there are no strong guardrails for invalid or risky stream setups
- there is limited visibility into failover events and endpoint health

## Vision

Build a focused control-plane product for a failover streaming appliance.

The product should sit on top of MediaMTX and `stream-failover-relay`, giving operators a safe and clear way to configure, run, monitor, and troubleshoot live failover pipelines.

## Product statement

> A lightweight stream failover control plane that combines ingest, switching, validation, and monitoring into one operator-friendly interface.

## What this product is

- a control plane
- an operator dashboard
- a configuration and validation layer
- a runtime management layer
- a monitoring and event-tracking layer

## What this product is not

- not a replacement for FFmpeg internals
- not a custom RTMP server from scratch
- not a full enterprise broadcast platform in v1
- not a multi-tenant SaaS in the first phase

## Primary users

### 1. Stream operator
Needs to:
- set up inputs and outputs quickly
- know which source is active
- see when failover happened
- identify why a stream is unhealthy

### 2. Technical admin
Needs to:
- manage services safely
- inspect logs and process state
- validate endpoint configuration
- roll back broken config quickly

## Core user goals

- configure failover without editing service files manually
- support RTMP and SRT input/output workflows
- observe input and output health in one place
- understand failover behavior in real time
- reduce downtime caused by human error
- make the stack reproducible across servers

## v1 product scope

The first release should focus on a **single-channel failover appliance** with one primary input, one backup input, and one output.

Why:
- simpler operational model
- lower build risk
- faster validation with real workloads
- easier testing of restart/recovery paths
- clean path to multi-channel later

## v1 success criteria

The MVP is successful if an operator can:

1. enter primary input, backup input, and output settings in the UI
2. validate and save configuration
3. apply the configuration without manual file editing
4. start and stop the runtime stack from the UI
5. see which input is currently active
6. detect whether output is healthy
7. review recent failover events and logs
8. recover quickly from a bad config using rollback

## Design principles

1. **Use proven streaming components**
   Prefer integrating MediaMTX and `stream-failover-relay` over rebuilding transport logic.

2. **Operator-first UX**
   The UI must prioritize clarity, safety, and fast diagnosis.

3. **Safe config lifecycle**
   Draft -> validate -> apply -> verify -> rollback.

4. **Visibility over guesswork**
   If a stream fails, the interface should explain what is down and why.

5. **Single-channel first, multi-channel ready**
   Keep v1 narrow while designing data structures for expansion.

6. **Local-first development**
   Prototype and validate locally before deploying to live infrastructure.

## Differentiators

Potential value beyond a shell wrapper:

- stream compatibility checks before apply
- one-click failover stack deployment
- event timeline for source switching
- protocol-aware forms for RTMP/SRT
- config profiles per destination/platform
- runtime guardrails and rollback
- optional notifications for outages and failovers

## Future expansion areas

- multi-channel pipelines
- HLS/WebRTC preview
- recording and replay hooks
- Telegram/webhook alerts
- destination templates (IBM VS, YouTube, custom RTMP)
- optional transcoding/normalization stage
- auth and multi-user roles

## Immediate next phase

Define architecture and the MVP boundary, then scaffold the local project and build the control-plane shell.
