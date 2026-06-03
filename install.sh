#!/bin/bash
set -euo pipefail

# StreamTerminal Relay Matrix - One-Command Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/stokesbot/streamterminal-relay-matrix/main/install.sh | bash
# Or: bash install.sh

REPO_URL="https://github.com/stokesbot/streamterminal-relay-matrix.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/streamterminal-relay-matrix}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-3000}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

banner() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║   StreamTerminal Relay Matrix - Installation Script      ║"
    echo "║   Automated RTMP Failover Streaming System               ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""
}

check_system() {
    log_info "Checking system requirements..."
    
    # Check OS
    if [[ ! -f /etc/os-release ]]; then
        log_error "Cannot detect OS. This script requires a Linux system."
        exit 1
    fi
    
    source /etc/os-release
    log_info "Detected OS: $PRETTY_NAME"
    
    # Check if running as root
    if [[ $EUID -eq 0 ]]; then
        log_warn "Running as root. This is not recommended for development."
        log_warn "Consider running as a regular user with sudo access."
    fi
    
    # Check required commands
    local missing_deps=()
    for cmd in git curl sudo systemctl; do
        if ! command -v $cmd &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${missing_deps[*]}"
        log_info "Please install them first. On Ubuntu/Debian:"
        log_info "  sudo apt-get update && sudo apt-get install -y git curl sudo systemd"
        exit 1
    fi
    
    log_success "System requirements check passed"
}

install_dependencies() {
    log_info "Installing system dependencies..."
    
    # Detect package manager
    if command -v apt-get &> /dev/null; then
        log_info "Using apt-get package manager"
        sudo apt-get update
        sudo apt-get install -y \
            build-essential \
            python3 \
            python3-pip \
            python3-venv \
            nodejs \
            npm \
            ffmpeg \
            jq \
            curl \
            wget
    elif command -v yum &> /dev/null; then
        log_info "Using yum package manager"
        sudo yum install -y \
            gcc \
            gcc-c++ \
            make \
            python3 \
            python3-pip \
            nodejs \
            npm \
            ffmpeg \
            jq \
            curl \
            wget
    elif command -v dnf &> /dev/null; then
        log_info "Using dnf package manager"
        sudo dnf install -y \
            gcc \
            gcc-c++ \
            make \
            python3 \
            python3-pip \
            nodejs \
            npm \
            ffmpeg \
            jq \
            curl \
            wget
    else
        log_error "Unsupported package manager. Please install dependencies manually."
        exit 1
    fi
    
    log_success "System dependencies installed"
}

install_uv() {
    log_info "Installing uv (Python package manager)..."
    
    if command -v uv &> /dev/null; then
        log_info "uv already installed: $(uv --version)"
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
        log_success "uv installed successfully"
    fi
}

clone_repository() {
    log_info "Cloning repository to $INSTALL_DIR..."
    
    if [[ -d "$INSTALL_DIR" ]]; then
        log_warn "Directory $INSTALL_DIR already exists"
        read -p "Do you want to remove it and re-clone? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$INSTALL_DIR"
        else
            log_info "Using existing directory"
            cd "$INSTALL_DIR"
            git pull origin main || log_warn "Could not pull latest changes"
            return
        fi
    fi
    
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    log_success "Repository cloned successfully"
}

setup_backend() {
    log_info "Setting up FastAPI backend..."
    
    cd "$INSTALL_DIR/apps/api"
    
    # Create .env file
    if [[ ! -f .env ]]; then
        cp .env.example .env
        log_info "Created .env file from template"
    fi
    
    # Install Python dependencies
    log_info "Installing Python dependencies with uv..."
    uv sync
    
    log_success "Backend setup complete"
}

setup_frontend() {
    log_info "Setting up Next.js frontend..."
    
    cd "$INSTALL_DIR/apps/web"
    
    # Create .env.local file
    if [[ ! -f .env.local ]]; then
        cat > .env.local << EOF
NEXT_PUBLIC_API_URL=http://${API_HOST}:${API_PORT}
EOF
        log_info "Created .env.local file"
    fi
    
    # Install Node dependencies
    log_info "Installing Node dependencies..."
    npm install
    
    log_success "Frontend setup complete"
}

install_mediamtx() {
    log_info "Installing MediaMTX..."
    
    local version="v1.9.3"
    local arch=$(uname -m)
    local os="linux"
    
    # Map architecture
    case $arch in
        x86_64) arch="amd64" ;;
        aarch64) arch="arm64v8" ;;
        armv7l) arch="armv7" ;;
        *) log_error "Unsupported architecture: $arch"; exit 1 ;;
    esac
    
    local download_url="https://github.com/bluenviron/mediamtx/releases/download/${version}/mediamtx_${version}_${os}_${arch}.tar.gz"
    
    log_info "Downloading MediaMTX $version for $os/$arch..."
    cd /tmp
    curl -L -o mediamtx.tar.gz "$download_url"
    tar -xzf mediamtx.tar.gz
    sudo mv mediamtx /usr/local/bin/
    sudo chmod +x /usr/local/bin/mediamtx
    rm -f mediamtx.tar.gz
    
    log_success "MediaMTX installed: $(mediamtx --version 2>&1 | head -1)"
}

install_relay() {
    log_info "Installing stream-failover-relay..."
    
    local version="v0.0.0-20241231-1"
    local arch=$(uname -m)
    
    # Map architecture
    case $arch in
        x86_64) arch="amd64" ;;
        aarch64) arch="arm64" ;;
        *) log_error "Unsupported architecture: $arch"; exit 1 ;;
    esac
    
    local download_url="https://github.com/xaionaro-go/stream-failover-relay/releases/download/${version}/stream-failover-relay_Linux_${arch}"
    
    log_info "Downloading stream-failover-relay $version for $arch..."
    cd /tmp
    curl -L -o stream-failover-relay "$download_url"
    sudo mv stream-failover-relay /usr/local/bin/
    sudo chmod +x /usr/local/bin/stream-failover-relay
    
    log_success "stream-failover-relay installed: $(stream-failover-relay --version 2>&1 | head -1 || echo 'installed')"
}

create_systemd_services() {
    log_info "Creating systemd service files..."
    
    # Create config directory
    sudo mkdir -p /etc/streamterminal-relay-matrix
    
    # Create MediaMTX config
    sudo tee /etc/streamterminal-relay-matrix/mediamtx.yml > /dev/null << 'EOF'
logLevel: info
logDestinations: [stdout]
logFile: /var/log/mediamtx/mediamtx.log

rtmpAddress: :1935
rtmpEncryption: "no"
rtmpServerKey: server.key
rtmpServerCert: server.crt

paths:
  all:
    source: publisher
EOF
    
    # Create MediaMTX service
    sudo tee /etc/systemd/system/mediamtx.service > /dev/null << 'EOF'
[Unit]
Description=MediaMTX RTMP/SRT Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mediamtx /etc/streamterminal-relay-matrix/mediamtx.yml
Restart=always
RestartSec=2
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    # Create relay command script
    sudo tee /usr/local/bin/relay-command.sh > /dev/null << 'EOF'
#!/bin/bash
set -a
source /etc/streamterminal-relay-matrix/streamterminal-relay.env
set +a
exec /usr/local/bin/stream-failover-relay \
  --input "$STM_PRIMARY_INPUT_URL" \
  --input "$STM_BACKUP_INPUT_URL" \
  --output "$STM_OUTPUT_URL"
EOF
    sudo chmod +x /usr/local/bin/relay-command.sh
    
    # Create relay service
    sudo tee /etc/systemd/system/stream-failover-relay.service > /dev/null << 'EOF'
[Unit]
Description=Stream Failover Relay
After=network-online.target mediamtx.service
Wants=network-online.target
Requires=mediamtx.service

[Service]
Type=simple
ExecStart=/usr/local/bin/relay-command.sh
Restart=always
RestartSec=2
LimitNOFILE=65536
MemoryMax=512M
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    # Create env file template
    sudo tee /etc/streamterminal-relay-matrix/streamterminal-relay.env.example > /dev/null << 'EOF'
STM_PRIMARY_INPUT_URL=rtmp://localhost:1935/live/main
STM_BACKUP_INPUT_URL=rtmp://localhost:1935/live/backup
STM_OUTPUT_URL=rtmp://localhost:1935/live/output
EOF
    
    # Copy to actual env file if it doesn't exist
    if [[ ! -f /etc/streamterminal-relay-matrix/streamterminal-relay.env ]]; then
        sudo cp /etc/streamterminal-relay-matrix/streamterminal-relay.env.example \
                /etc/streamterminal-relay-matrix/streamterminal-relay.env
        sudo chmod 600 /etc/streamterminal-relay-matrix/streamterminal-relay.env
    fi
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    log_success "Systemd services created"
}

start_services() {
    log_info "Starting services..."
    
    # Enable and start MediaMTX
    sudo systemctl enable mediamtx.service
    sudo systemctl start mediamtx.service
    
    # Enable and start relay
    sudo systemctl enable stream-failover-relay.service
    sudo systemctl start stream-failover-relay.service
    
    # Wait a moment for services to start
    sleep 2
    
    # Check status
    if systemctl is-active --quiet mediamtx.service; then
        log_success "MediaMTX service is running"
    else
        log_error "MediaMTX service failed to start"
        sudo journalctl -u mediamtx.service -n 20 --no-pager
    fi
    
    if systemctl is-active --quiet stream-failover-relay.service; then
        log_success "Stream Failover Relay service is running"
    else
        log_warn "Stream Failover Relay service failed to start (this is expected if env is not configured)"
    fi
}

create_start_script() {
    log_info "Creating start script..."
    
    cat > "$INSTALL_DIR/start.sh" << EOF
#!/bin/bash
set -e

cd "$(dirname "\$0")"

echo "Starting StreamTerminal Relay Matrix..."
echo ""

# Start API
echo "Starting API on $API_HOST:$API_PORT..."
cd apps/api
uv run uvicorn app.main:app --host $API_HOST --port $API_PORT > /tmp/stm-api.log 2>&1 &
API_PID=\$!
echo "API started (PID: \$API_PID)"

# Start Web UI
echo "Starting Web UI on $WEB_HOST:$WEB_PORT..."
cd ../web
NEXT_PUBLIC_API_URL=http://$API_HOST:$API_PORT npm run dev -- --hostname $WEB_HOST --port $WEB_PORT > /tmp/stm-web.log 2>&1 &
WEB_PID=\$!
echo "Web UI started (PID: \$WEB_PID)"

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║   StreamTerminal Relay Matrix is now running!            ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "Access the Web UI at: http://$WEB_HOST:$WEB_PORT"
echo "API endpoint: http://$API_HOST:$API_PORT"
echo ""
echo "API logs: /tmp/stm-api.log"
echo "Web logs: /tmp/stm-web.log"
echo ""
echo "To stop the services:"
echo "  kill \$API_PID \$WEB_PID"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for both processes
wait \$API_PID \$WEB_PID
EOF
    
    chmod +x "$INSTALL_DIR/start.sh"
    log_success "Start script created: $INSTALL_DIR/start.sh"
}

print_summary() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║   Installation Complete!                                  ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""
    log_success "StreamTerminal Relay Matrix has been installed successfully!"
    echo ""
    echo "Installation directory: $INSTALL_DIR"
    echo ""
    echo "Services:"
    echo "  • MediaMTX: $(systemctl is-active mediamtx.service 2>/dev/null || echo 'not running')"
    echo "  • Stream Failover Relay: $(systemctl is-active stream-failover-relay.service 2>/dev/null || echo 'not running')"
    echo ""
    echo "To start the control plane (API + Web UI):"
    echo "  cd $INSTALL_DIR"
    echo "  ./start.sh"
    echo ""
    echo "Or start services individually:"
    echo "  # API"
    echo "  cd $INSTALL_DIR/apps/api"
    echo "  uv run uvicorn app.main:app --host $API_HOST --port $API_PORT"
    echo ""
    echo "  # Web UI"
    echo "  cd $INSTALL_DIR/apps/web"
    echo "  NEXT_PUBLIC_API_URL=http://$API_HOST:$API_PORT npm run dev -- --hostname $WEB_HOST --port $WEB_PORT"
    echo ""
    echo "Access points:"
    echo "  • Web UI: http://$WEB_HOST:$WEB_PORT"
    echo "  • API: http://$API_HOST:$API_PORT"
    echo "  • RTMP Server: rtmp://$(hostname -I | awk '{print $1}'):1935"
    echo ""
    echo "Configuration:"
    echo "  • MediaMTX config: /etc/streamterminal-relay-matrix/mediamtx.yml"
    echo "  • Relay env: /etc/streamterminal-relay-matrix/streamterminal-relay.env"
    echo ""
    echo "Next steps:"
    echo "  1. Edit /etc/streamterminal-relay-matrix/streamterminal-relay.env"
    echo "  2. Configure your primary and backup stream URLs"
    echo "  3. Restart the relay: sudo systemctl restart stream-failover-relay.service"
    echo "  4. Start the control plane: cd $INSTALL_DIR && ./start.sh"
    echo "  5. Open the Web UI and configure your streams"
    echo ""
    echo "Documentation: $INSTALL_DIR/docs/"
    echo ""
}

main() {
    banner
    check_system
    install_dependencies
    install_uv
    clone_repository
    setup_backend
    setup_frontend
    install_mediamtx
    install_relay
    create_systemd_services
    start_services
    create_start_script
    print_summary
}

main "$@"
