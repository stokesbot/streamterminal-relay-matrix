#!/bin/bash
# Comprehensive Live Stream Test for StreamTerminal Relay Matrix
# This script tests the entire failover system with real video streams

set -e

API_URL="http://127.0.0.1:18181"
RTMP_SERVER="rtmp://localhost:1935"

echo "=========================================="
echo "StreamTerminal Relay Matrix - Live Stream Test"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check API status
check_api_status() {
    log_info "Checking runtime status..."
    curl -s "$API_URL/api/runtime/status" | jq '{active_source, primary_state, backup_state, output_state}'
}

# Function to run smoke test
run_smoke_test() {
    log_info "Running smoke test..."
    curl -s "$API_URL/api/runtime/smoke" | jq '{ok, summary, checks: [.checks[] | {name, status}]}'
}

# Cleanup function
cleanup() {
    log_warning "Cleaning up test streams..."
    pkill -f "ffmpeg.*live/main" 2>/dev/null || true
    pkill -f "ffmpeg.*live/backup" 2>/dev/null || true
    log_success "Cleanup complete"
}

trap cleanup EXIT

echo "=== Phase 1: Pre-Test Status ==="
echo ""
log_info "Initial system state:"
check_api_status
echo ""

echo "=== Phase 2: Starting Primary Stream ==="
echo ""
log_info "Generating test pattern for PRIMARY stream..."
log_info "Stream: ${RTMP_SERVER}/live/main"

# Start primary stream in background
ffmpeg -re -f lavfi -i "testsrc=size=1280x720:rate=30" \
    -f lavfi -i "sine=frequency=1000:sample_rate=44100" \
    -c:v libx264 -preset ultrafast -tune zerolatency -b:v 2000k \
    -c:a aac -b:a 128k \
    -f flv "${RTMP_SERVER}/live/main" \
    > /tmp/ffmpeg-primary.log 2>&1 &

PRIMARY_PID=$!
log_success "Primary stream started (PID: $PRIMARY_PID)"

# Wait for stream to establish
log_info "Waiting 5 seconds for stream to establish..."
sleep 5

echo ""
log_info "Status after PRIMARY stream started:"
check_api_status
echo ""

echo "=== Phase 3: Starting Backup Stream ==="
echo ""
log_info "Generating test pattern for BACKUP stream..."
log_info "Stream: ${RTMP_SERVER}/live/backup"

# Start backup stream in background (different pattern)
ffmpeg -re -f lavfi -i "testsrc=size=1280x720:rate=30:decimals=2" \
    -f lavfi -i "sine=frequency=500:sample_rate=44100" \
    -c:v libx264 -preset ultrafast -tune zerolatency -b:v 2000k \
    -c:a aac -b:a 128k \
    -f flv "${RTMP_SERVER}/live/backup" \
    > /tmp/ffmpeg-backup.log 2>&1 &

BACKUP_PID=$!
log_success "Backup stream started (PID: $BACKUP_PID)"

# Wait for stream to establish
log_info "Waiting 5 seconds for stream to establish..."
sleep 5

echo ""
log_info "Status after BOTH streams started:"
check_api_status
echo ""

echo "=== Phase 4: Running Smoke Test ==="
echo ""
run_smoke_test
echo ""

echo "=== Phase 5: Monitoring for 10 seconds ==="
echo ""
log_info "Watching system state..."
for i in {1..10}; do
    echo "--- Second $i ---"
    check_api_status
    sleep 1
done
echo ""

echo "=== Phase 6: Testing Failover - Stopping Primary ==="
echo ""
log_warning "Killing primary stream (PID: $PRIMARY_PID)..."
kill $PRIMARY_PID 2>/dev/null || true
log_success "Primary stream stopped"

log_info "Waiting 10 seconds for failover to backup..."
for i in {1..10}; do
    echo "--- Failover second $i ---"
    check_api_status
    sleep 1
done
echo ""

echo "=== Phase 7: Restarting Primary ==="
echo ""
log_info "Restarting primary stream..."
ffmpeg -re -f lavfi -i "testsrc=size=1280x720:rate=30" \
    -f lavfi -i "sine=frequency=1000:sample_rate=44100" \
    -c:v libx264 -preset ultrafast -tune zerolatency -b:v 2000k \
    -c:a aac -b:a 128k \
    -f flv "${RTMP_SERVER}/live/main" \
    > /tmp/ffmpeg-primary-2.log 2>&1 &

PRIMARY_PID=$!
log_success "Primary stream restarted (PID: $PRIMARY_PID)"

log_info "Waiting 10 seconds for failback to primary..."
for i in {1..10}; do
    echo "--- Failback second $i ---"
    check_api_status
    sleep 1
done
echo ""

echo "=== Phase 8: Final Smoke Test ==="
echo ""
run_smoke_test
echo ""

echo "=== Phase 9: Service Logs ==="
echo ""
log_info "MediaMTX recent logs:"
sudo journalctl -u mediamtx --no-pager -n 20 2>/dev/null || echo "Cannot access logs (need sudo)"
echo ""

log_info "Stream Failover Relay recent logs:"
sudo journalctl -u stream-failover-relay --no-pager -n 20 2>/dev/null || echo "Cannot access logs (need sudo)"
echo ""

echo "=== Phase 10: Stream Statistics ==="
echo ""
log_info "FFmpeg Primary Log (last 10 lines):"
tail -10 /tmp/ffmpeg-primary.log 2>/dev/null || echo "No primary log"
echo ""

log_info "FFmpeg Backup Log (last 10 lines):"
tail -10 /tmp/ffmpeg-backup.log 2>/dev/null || echo "No backup log"
echo ""

echo "=========================================="
echo "Test Complete!"
echo "=========================================="
echo ""
log_success "All test phases completed"
log_info "Streams will be cleaned up automatically"
echo ""
echo "Summary:"
echo "- Primary stream: Started, stopped, restarted"
echo "- Backup stream: Started and maintained"
echo "- Failover: Tested (primary → backup)"
echo "- Failback: Tested (backup → primary)"
echo ""
echo "Check the logs above for detailed behavior"

# Made with Bob
