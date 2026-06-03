# StreamTerminal Relay Matrix - Installation Guide

Complete guide for installing StreamTerminal Relay Matrix on any Linux system (local machine or VPS).

## Quick Install (Recommended)

One-command installation that sets up everything automatically:

```bash
curl -fsSL https://raw.githubusercontent.com/stokesbot/streamterminal-relay-matrix/main/install.sh | bash
```

Or download and run manually:

```bash
wget https://raw.githubusercontent.com/stokesbot/streamterminal-relay-matrix/main/install.sh
chmod +x install.sh
./install.sh
```

### Custom Installation Directory

```bash
INSTALL_DIR=/opt/streamterminal ./install.sh
```

### Custom Ports

```bash
API_PORT=8080 WEB_PORT=3001 ./install.sh
```

---

## What Gets Installed

The installation script will:

1. **System Dependencies**
   - Python 3, Node.js, npm
   - FFmpeg (for stream testing)
   - Build tools (gcc, make)
   - jq, curl, wget

2. **Python Package Manager**
   - uv (modern Python package manager)

3. **Repository**
   - Clones from GitHub
   - Sets up backend (FastAPI)
   - Sets up frontend (Next.js)

4. **Streaming Components**
   - MediaMTX (RTMP/SRT server)
   - stream-failover-relay (failover logic)

5. **System Services**
   - systemd service files
   - Configuration files in `/etc/streamterminal-relay-matrix/`
   - Binaries in `/usr/local/bin/`

---

## Post-Installation

### 1. Start the Control Plane

```bash
cd ~/streamterminal-relay-matrix
./start.sh
```

This starts:
- API on http://0.0.0.0:8000
- Web UI on http://0.0.0.0:3000

### 2. Access the Web UI

Open your browser to:
- **Local:** http://localhost:3000
- **VPS:** http://YOUR_VPS_IP:3000

### 3. Configure Stream URLs

Edit the relay configuration:

```bash
sudo nano /etc/streamterminal-relay-matrix/streamterminal-relay.env
```

Set your stream URLs:

```bash
STM_PRIMARY_INPUT_URL=rtmp://localhost:1935/live/main
STM_BACKUP_INPUT_URL=rtmp://localhost:1935/live/backup
STM_OUTPUT_URL=rtmp://localhost:1935/live/output
```

### 4. Restart the Relay

```bash
sudo systemctl restart stream-failover-relay.service
```

### 5. Verify Services

```bash
# Check service status
sudo systemctl status mediamtx.service
sudo systemctl status stream-failover-relay.service

# Check RTMP port
ss -tlnp | grep :1935

# Test API
curl http://localhost:8000/api/health
```

---

## Manual Installation

If you prefer to install manually or the script doesn't work for your system:

### Prerequisites

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y git curl build-essential python3 python3-pip nodejs npm ffmpeg jq

# RHEL/CentOS/Fedora
sudo dnf install -y git curl gcc gcc-c++ make python3 python3-pip nodejs npm ffmpeg jq
```

### Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"
```

### Clone Repository

```bash
git clone https://github.com/stokesbot/streamterminal-relay-matrix.git
cd streamterminal-relay-matrix
```

### Setup Backend

```bash
cd apps/api
cp .env.example .env
uv sync
```

### Setup Frontend

```bash
cd ../web
cp .env.example .env.local
npm install
```

### Install MediaMTX

```bash
# Download latest release
VERSION=v1.9.3
ARCH=amd64  # or arm64v8, armv7
wget https://github.com/bluenviron/mediamtx/releases/download/${VERSION}/mediamtx_${VERSION}_linux_${ARCH}.tar.gz
tar -xzf mediamtx_${VERSION}_linux_${ARCH}.tar.gz
sudo mv mediamtx /usr/local/bin/
sudo chmod +x /usr/local/bin/mediamtx
```

### Install stream-failover-relay

```bash
# Download latest release
VERSION=v0.0.0-20241231-1
ARCH=amd64  # or arm64
wget https://github.com/xaionaro-go/stream-failover-relay/releases/download/${VERSION}/stream-failover-relay_Linux_${ARCH}
sudo mv stream-failover-relay_Linux_${ARCH} /usr/local/bin/stream-failover-relay
sudo chmod +x /usr/local/bin/stream-failover-relay
```

### Create Configuration

```bash
sudo mkdir -p /etc/streamterminal-relay-matrix

# MediaMTX config
sudo tee /etc/streamterminal-relay-matrix/mediamtx.yml > /dev/null << 'YAML'
logLevel: info
logDestinations: [stdout]
rtmpAddress: :1935
paths:
  all:
    source: publisher
YAML

# Relay env file
sudo tee /etc/streamterminal-relay-matrix/streamterminal-relay.env > /dev/null << 'ENV'
STM_PRIMARY_INPUT_URL=rtmp://localhost:1935/live/main
STM_BACKUP_INPUT_URL=rtmp://localhost:1935/live/backup
STM_OUTPUT_URL=rtmp://localhost:1935/live/output
ENV
sudo chmod 600 /etc/streamterminal-relay-matrix/streamterminal-relay.env
```

### Create systemd Services

See the `install.sh` script for complete systemd service definitions, or use the built-in deployment system via the Web UI.

---

## Architecture-Specific Notes

### ARM64 (Raspberry Pi, etc.)

```bash
# Use arm64v8 for MediaMTX
ARCH=arm64v8

# Use arm64 for stream-failover-relay
ARCH=arm64
```

### ARMv7 (Older Raspberry Pi)

```bash
# Use armv7 for MediaMTX
ARCH=armv7

# stream-failover-relay may not have armv7 builds
# You may need to compile from source
```

---

## Firewall Configuration

If using a firewall, open these ports:

```bash
# UFW (Ubuntu)
sudo ufw allow 1935/tcp  # RTMP
sudo ufw allow 8000/tcp  # API
sudo ufw allow 3000/tcp  # Web UI

# firewalld (RHEL/CentOS)
sudo firewall-cmd --permanent --add-port=1935/tcp
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --permanent --add-port=3000/tcp
sudo firewall-cmd --reload

# iptables
sudo iptables -A INPUT -p tcp --dport 1935 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 3000 -j ACCEPT
```

---

## Testing the Installation

### 1. Test RTMP Server

```bash
# Publish a test stream
ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=30 \
  -f lavfi -i sine=frequency=1000:sample_rate=44100 \
  -c:v libx264 -preset veryfast -b:v 2M \
  -c:a aac -b:a 128k \
  -f flv rtmp://localhost:1935/live/main
```

### 2. Test Failover

Use the comprehensive test script:

```bash
cd ~/streamterminal-relay-matrix
bash run-live-stream-test.sh
```

### 3. Test Web UI

1. Open http://localhost:3000
2. Navigate to Dashboard
3. Check service status
4. View diagnostics

---

## Troubleshooting

### Services Won't Start

```bash
# Check logs
sudo journalctl -u mediamtx.service -n 50
sudo journalctl -u stream-failover-relay.service -n 50

# Check if ports are in use
sudo ss -tlnp | grep -E ':(1935|8000|3000)'

# Restart services
sudo systemctl restart mediamtx.service
sudo systemctl restart stream-failover-relay.service
```

### API/Web UI Not Accessible

```bash
# Check if services are running
ps aux | grep uvicorn
ps aux | grep next

# Check logs
tail -f /tmp/stm-api.log
tail -f /tmp/stm-web.log

# Restart
cd ~/streamterminal-relay-matrix
./start.sh
```

### Relay Not Switching

```bash
# Check relay configuration
sudo cat /etc/streamterminal-relay-matrix/streamterminal-relay.env

# Check relay logs
sudo journalctl -u stream-failover-relay.service -f

# Verify MediaMTX is receiving streams
curl http://localhost:9997/v3/paths/list
```

### Permission Denied

```bash
# Fix ownership
sudo chown -R $USER:$USER ~/streamterminal-relay-matrix

# Fix permissions on config
sudo chmod 600 /etc/streamterminal-relay-matrix/streamterminal-relay.env
```

---

## Uninstallation

```bash
# Stop and disable services
sudo systemctl stop mediamtx.service stream-failover-relay.service
sudo systemctl disable mediamtx.service stream-failover-relay.service

# Remove service files
sudo rm /etc/systemd/system/mediamtx.service
sudo rm /etc/systemd/system/stream-failover-relay.service
sudo systemctl daemon-reload

# Remove binaries
sudo rm /usr/local/bin/mediamtx
sudo rm /usr/local/bin/stream-failover-relay
sudo rm /usr/local/bin/relay-command.sh

# Remove configuration
sudo rm -rf /etc/streamterminal-relay-matrix

# Remove application
rm -rf ~/streamterminal-relay-matrix
```

---

## Production Deployment

For production use, consider:

1. **SSL/TLS**: Use nginx or Caddy as reverse proxy
2. **Authentication**: Add API key authentication
3. **Monitoring**: Set up Prometheus + Grafana
4. **Backups**: Regular backups of configuration
5. **Updates**: Keep components updated
6. **Logging**: Configure log rotation
7. **Security**: Firewall rules, fail2ban, etc.

See `docs/operations.md` for detailed production guidelines.

---

## Support

- **Documentation**: `docs/` directory
- **Issues**: https://github.com/stokesbot/streamterminal-relay-matrix/issues
- **Discussions**: https://github.com/stokesbot/streamterminal-relay-matrix/discussions

---

## Next Steps

After installation:

1. Read `docs/operations.md` for operational procedures
2. Configure your stream sources
3. Test failover behavior
4. Set up monitoring
5. Configure backups

Enjoy your automated streaming failover system!
