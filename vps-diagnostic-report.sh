#!/bin/bash
# VPS Diagnostic Report for StreamTerminal Relay Matrix
# Run this script ON THE VPS (46.225.116.163) to generate a comprehensive diagnostic report

echo "=========================================="
echo "StreamTerminal Relay Matrix - Diagnostic Report"
echo "Generated: $(date)"
echo "=========================================="
echo ""

# Check if running on VPS
if [ -f /etc/hostname ]; then
    echo "Hostname: $(cat /etc/hostname)"
fi
echo ""

echo "=== 1. Service Status ==="
echo ""
echo "API Service (Port 8000):"
if systemctl is-active --quiet streamterminal-api 2>/dev/null; then
    echo "  Status: RUNNING"
    systemctl status streamterminal-api --no-pager -l | head -20
elif pgrep -f "uvicorn.*8000" > /dev/null; then
    echo "  Status: RUNNING (process found)"
    ps aux | grep -E "uvicorn.*8000" | grep -v grep
else
    echo "  Status: NOT RUNNING"
    echo "  Checking for any Python API process..."
    ps aux | grep -E "python.*api|uvicorn" | grep -v grep || echo "  No API process found"
fi
echo ""

echo "Web UI Service (Port 3000):"
if systemctl is-active --quiet streamterminal-web 2>/dev/null; then
    echo "  Status: RUNNING"
    systemctl status streamterminal-web --no-pager -l | head -20
elif pgrep -f "next.*3000" > /dev/null; then
    echo "  Status: RUNNING (process found)"
    ps aux | grep -E "next.*3000|node.*3000" | grep -v grep
else
    echo "  Status: NOT RUNNING"
    echo "  Checking for any Node.js process..."
    ps aux | grep -E "node|next" | grep -v grep || echo "  No Node.js process found"
fi
echo ""

echo "MediaMTX Service:"
systemctl status mediamtx --no-pager -l 2>/dev/null | head -15 || echo "  Service not found or not running"
echo ""

echo "Stream Failover Relay Service:"
systemctl status stream-failover-relay --no-pager -l 2>/dev/null | head -15 || echo "  Service not found or not running"
echo ""

echo "=== 2. Port Listening Status ==="
echo ""
echo "Port 8000 (API):"
ss -tlnp | grep :8000 || echo "  Not listening"
echo ""
echo "Port 3000 (Web UI):"
ss -tlnp | grep :3000 || echo "  Not listening"
echo ""
echo "Port 1935 (RTMP):"
ss -tlnp | grep :1935 || echo "  Not listening"
echo ""

echo "=== 3. API Health Check (Local) ==="
echo ""
if curl -sf -m 5 http://localhost:8000/api/health > /tmp/health.json 2>&1; then
    echo "API Health: OK"
    cat /tmp/health.json | jq . 2>/dev/null || cat /tmp/health.json
else
    echo "API Health: FAILED"
    echo "Error: $(cat /tmp/health.json 2>/dev/null || echo 'Connection failed')"
fi
echo ""

echo "=== 4. API Smoke Test (Local) ==="
echo ""
if curl -sf -m 5 http://localhost:8000/api/runtime/smoke > /tmp/smoke.json 2>&1; then
    echo "Smoke Test: OK"
    cat /tmp/smoke.json | jq '.ok, .summary, .checks[] | {name, status, detail}' 2>/dev/null || cat /tmp/smoke.json
else
    echo "Smoke Test: FAILED"
    echo "Error: $(cat /tmp/smoke.json 2>/dev/null || echo 'Connection failed')"
fi
echo ""

echo "=== 5. Current Configuration ==="
echo ""
if curl -sf -m 5 http://localhost:8000/api/config > /tmp/config.json 2>&1; then
    echo "Config Retrieved: OK"
    cat /tmp/config.json | jq '{channel_name, primary_input: .primary_input.url, backup_input: .backup_input.url, output: .output.url}' 2>/dev/null || cat /tmp/config.json
else
    echo "Config Retrieval: FAILED"
fi
echo ""

echo "=== 6. Runtime Status ==="
echo ""
if curl -sf -m 5 http://localhost:8000/api/runtime/status > /tmp/status.json 2>&1; then
    echo "Runtime Status: OK"
    cat /tmp/status.json | jq '{active_source, primary_state, backup_state, output_state, services: .services[]}' 2>/dev/null || cat /tmp/status.json
else
    echo "Runtime Status: FAILED"
fi
echo ""

echo "=== 7. Web UI Accessibility ==="
echo ""
echo "Testing Web UI pages..."
for page in "/" "/config" "/diagnostics" "/deploy"; do
    echo -n "  $page: "
    if curl -sf -m 5 -I "http://localhost:3000$page" | head -1 | grep -q "200"; then
        echo "OK"
    else
        echo "FAILED"
    fi
done
echo ""

echo "=== 8. Firewall Status ==="
echo ""
if command -v ufw > /dev/null; then
    echo "UFW Status:"
    ufw status | grep -E "8000|3000|1935" || echo "  No rules for ports 8000, 3000, 1935"
elif command -v iptables > /dev/null; then
    echo "IPTables Rules (relevant ports):"
    iptables -L -n | grep -E "8000|3000|1935" || echo "  No rules found"
else
    echo "  No firewall detected"
fi
echo ""

echo "=== 9. Recent Logs ==="
echo ""
echo "API Logs (last 20 lines):"
if [ -f /var/log/streamterminal-api.log ]; then
    tail -20 /var/log/streamterminal-api.log
elif journalctl -u streamterminal-api --no-pager -n 20 2>/dev/null; then
    :
else
    echo "  No API logs found"
fi
echo ""

echo "MediaMTX Logs (last 10 lines):"
journalctl -u mediamtx --no-pager -n 10 2>/dev/null || echo "  No MediaMTX logs found"
echo ""

echo "Relay Logs (last 10 lines):"
journalctl -u stream-failover-relay --no-pager -n 10 2>/dev/null || echo "  No relay logs found"
echo ""

echo "=== 10. Disk Space ==="
echo ""
df -h | grep -E "Filesystem|/$|/opt"
echo ""

echo "=== 11. Network Connectivity ==="
echo ""
echo "Testing external connectivity..."
ping -c 2 8.8.8.8 > /dev/null 2>&1 && echo "  Internet: OK" || echo "  Internet: FAILED"
echo ""

echo "=========================================="
echo "Diagnostic Report Complete"
echo "=========================================="
echo ""
echo "NEXT STEPS:"
echo "1. If API/Web UI are not running, check the startup commands"
echo "2. If ports are not listening, check firewall rules"
echo "3. If services are failing, check the logs above"
echo "4. Share this report for further analysis"

# Made with Bob
