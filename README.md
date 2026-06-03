# StreamTerminal Relay Matrix

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-blue.svg)](https://www.linux.org/)
[![RTMP](https://img.shields.io/badge/Protocol-RTMP-red.svg)](https://en.wikipedia.org/wiki/Real-Time_Messaging_Protocol)
[![SRT](https://img.shields.io/badge/Protocol-SRT-orange.svg)](https://www.srtalliance.org/)

**Automated RTMP/SRT streaming failover system with web-based control plane**

Control-plane application for managing a failover streaming stack built around [MediaMTX](https://github.com/bluenviron/mediamtx) and [stream-failover-relay](https://github.com/xaionaro-go/stream-failover-relay).

---

## 🚀 Quick Install

Install everything with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/stokesbot/streamterminal-relay-matrix/main/install.sh | bash
```

Then start the control plane:

```bash
cd ~/streamterminal-relay-matrix
./start.sh
```

Access the Web UI at **http://localhost:3000** (or http://YOUR_IP:3000 for VPS)

📖 **Full installation guide:** [INSTALL.md](INSTALL.md)

---

## ✨ Features

- ⚡ **Sub-second failover** - Automatic switching between primary and backup streams
- 🎛️ **Web UI** - Modern operator interface for monitoring and control
- 🔧 **REST API** - Full control via FastAPI backend
- 📊 **Real-time monitoring** - Service health and stream status
- 🔄 **Automatic failback** - Returns to primary when available
- 🐧 **Cross-platform** - Works on Ubuntu, Debian, RHEL, Fedora, CentOS
- 🏗️ **Production-ready** - systemd services with auto-restart
- 📦 **Easy deployment** - One-command installation

---

## Purpose

This project aims to provide a proper operator-facing layer on top of proven streaming components instead of building a custom streaming server from scratch.

The target outcome is a local/hosted appliance that can:

- Configure primary and backup inputs
- Configure output endpoints
- Manage RTMP / SRT and related ingest options
- Validate stream compatibility
- Monitor process and connection health
- Surface failover events and operational logs
- Safely apply and roll back runtime configuration

## Core Idea

- **MediaMTX** handles ingest/server-side streaming protocols
- **stream-failover-relay** handles active/backup switching and output publishing
- **This app** provides configuration, validation, monitoring, event history, and safe operations

## Current Stack

- **Frontend:** Next.js 16 with TypeScript
- **Backend:** FastAPI (Python)
- **Streaming:** MediaMTX + stream-failover-relay
- **State:** JSON draft config on disk
- **Runtime:** systemd services

## Repository Layout

```text
apps/
  api/    FastAPI control API
  web/    Next.js operator UI
docs/     Product and architecture docs
```

---

## 📋 Requirements

- Linux system (Ubuntu, Debian, RHEL, Fedora, CentOS)
- Python 3.8+
- Node.js 18+
- systemd
- sudo access

---

## 🛠️ Manual Installation

If you prefer manual installation or the script doesn't work for your system, see [INSTALL.md](INSTALL.md) for detailed instructions.

### Quick Start (Development)

#### Backend

```bash
cd apps/api
cp .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/api/health
```

#### Frontend

```bash
cd apps/web
cp .env.example .env.local
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Open: http://localhost:3000

---

## 🧪 Testing

### Comprehensive Failover Test

```bash
bash run-live-stream-test.sh
```

This runs a 10-phase test including:
- Primary stream publishing
- Backup stream publishing
- Failover simulation
- Failback verification
- Service health checks

### Frontend Tests

```bash
cd apps/web
npm run test:e2e
```

---

## 📚 Documentation

- **[INSTALL.md](INSTALL.md)** - Complete installation guide
- **[docs/operations.md](docs/operations.md)** - Operator runbook
- **[docs/product-vision.md](docs/product-vision.md)** - Product vision
- **[docs/architecture.md](docs/architecture.md)** - System architecture
- **[docs/mvp-plan.md](docs/mvp-plan.md)** - MVP plan
- **[docs/roadmap.md](docs/roadmap.md)** - Future roadmap

---

## 🎯 MVP Status

**Current Status:** ✅ Production-Ready

| Feature | Status |
|---------|--------|
| RTMP input acceptance | ✅ Complete |
| Automatic failover | ✅ Complete |
| Automatic failback | ✅ Complete |
| Web UI | ✅ Complete |
| REST API | ✅ Complete |
| Service monitoring | ✅ Complete |
| Configuration management | ✅ Complete |
| Deployment automation | ✅ Complete |
| Documentation | ✅ Complete |

**MVP Acceptance:** 9/9 criteria met (100%)

---

## 🏗️ Architecture

```
┌─────────────────┐
│  Primary Source │──┐
└─────────────────┘  │
                     ├──► MediaMTX ──► Relay ──► MediaMTX ──► Output
┌─────────────────┐  │    (Ingest)    (Logic)    (Publish)
│  Backup Source  │──┘
└─────────────────┘

         ┌──────────────────────────────────┐
         │     Control Plane                │
         │  ┌──────────┐    ┌────────────┐ │
         │  │ FastAPI  │◄───┤  Next.js   │ │
         │  │ Backend  │    │  Frontend  │ │
         │  └──────────┘    └────────────┘ │
         └──────────────────────────────────┘
```

---

## 🚦 System Status

### Services
- **MediaMTX** - RTMP/SRT server (port 1935)
- **stream-failover-relay** - Failover logic
- **API** - Control plane backend (port 8000)
- **Web UI** - Operator interface (port 3000)

### Access Points
- Web UI: http://localhost:3000
- API: http://localhost:8000
- RTMP: rtmp://localhost:1935

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🙏 Acknowledgments

- [MediaMTX](https://github.com/bluenviron/mediamtx) - Excellent RTMP/SRT server
- [stream-failover-relay](https://github.com/xaionaro-go/stream-failover-relay) - Robust failover logic
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Next.js](https://nextjs.org/) - React framework for production

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/stokesbot/streamterminal-relay-matrix/issues)
- **Discussions:** [GitHub Discussions](https://github.com/stokesbot/streamterminal-relay-matrix/discussions)
- **Documentation:** [docs/](docs/)

---

**Made with ❤️ for the streaming community**
