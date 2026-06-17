#!/bin/bash
# Comprehensive UI/API Test Script for StreamTerminal Relay Matrix
# Tests all major endpoints and UI functionality
#
# Usage: ./test-vps-ui.sh [HOST] [API_PORT] [WEB_PORT]
#   HOST      defaults to localhost
#   API_PORT  defaults to 8000
#   WEB_PORT  defaults to 3000
#
# Examples:
#   ./test-vps-ui.sh                         # test localhost:8000 / :3000
#   ./test-vps-ui.sh 192.168.1.50            # test 192.168.1.50:8000 / :3000
#   ./test-vps-ui.sh mybox 8080 3001         # test mybox:8080 / :3001

set -e

TARGET="${1:-localhost}"
API_PORT="${2:-8000}"
WEB_PORT="${3:-3000}"
API_BASE="http://${TARGET}:${API_PORT}"
WEB_BASE="http://${TARGET}:${WEB_PORT}"

echo "=========================================="
echo "StreamTerminal Relay Matrix - UI/API Test"
echo "Target: ${TARGET}"
echo "API:    ${API_BASE}"
echo "Web:    ${WEB_BASE}"
echo "=========================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

test_count=0
pass_count=0
fail_count=0

run_test() {
    local test_name="$1"
    local test_command="$2"
    local expected_status="${3:-200}"
    
    test_count=$((test_count + 1))
    echo -n "[$test_count] Testing: $test_name ... "
    
    response=$(eval "$test_command" 2>&1)
    status=$?
    
    if [ $status -eq 0 ]; then
        echo -e "${GREEN}PASS${NC}"
        pass_count=$((pass_count + 1))
        if [ -n "$response" ] && [ "$response" != "null" ]; then
            echo "    Response: ${response:0:100}..."
        fi
    else
        echo -e "${RED}FAIL${NC}"
        fail_count=$((fail_count + 1))
        echo "    Error: $response"
    fi
    echo ""
}

echo "=== 1. API Health Checks ==="
echo ""

run_test "API Health Endpoint" \
    "curl -sf -m 5 ${API_BASE}/api/health"

run_test "API Runtime Status" \
    "curl -sf -m 5 ${API_BASE}/api/runtime/status"

run_test "API Config Endpoint" \
    "curl -sf -m 5 ${API_BASE}/api/config"

run_test "API Diagnostics" \
    "curl -sf -m 5 ${API_BASE}/api/diagnostics"

run_test "API Smoke Test" \
    "curl -sf -m 5 ${API_BASE}/api/runtime/smoke"

echo "=== 2. Deployment Endpoints ==="
echo ""

run_test "Deployment Profiles" \
    "curl -sf -m 5 ${API_BASE}/api/deploy/profiles"

run_test "Deployment Preflight" \
    "curl -sf -m 5 '${API_BASE}/api/deploy/preflight?profile_id=local-system'"

run_test "Deployment Plan" \
    "curl -sf -m 5 '${API_BASE}/api/deploy/plan?profile_id=local-system'"

run_test "Deployment Audit" \
    "curl -sf -m 5 '${API_BASE}/api/deploy/audit?profile_id=local-system'"

run_test "Host Snapshots List" \
    "curl -sf -m 5 ${API_BASE}/api/deploy/host-snapshots"

run_test "Bundle Inventory" \
    "curl -sf -m 5 ${API_BASE}/api/runtime/bundles"

echo "=== 3. Service Control Endpoints ==="
echo ""

run_test "MediaMTX Service Logs" \
    "curl -sf -m 5 '${API_BASE}/api/services/mediamtx/logs?lines=5'"

run_test "Relay Service Logs" \
    "curl -sf -m 5 '${API_BASE}/api/services/stream-failover-relay/logs?lines=5'"

echo "=== 4. Web UI Accessibility ==="
echo ""

run_test "Web UI Home Page" \
    "curl -sf -m 5 -I ${WEB_BASE}/ | head -1 | grep -q '200'"

run_test "Web UI Config Page" \
    "curl -sf -m 5 -I ${WEB_BASE}/config | head -1 | grep -q '200'"

run_test "Web UI Diagnostics Page" \
    "curl -sf -m 5 -I ${WEB_BASE}/diagnostics | head -1 | grep -q '200'"

run_test "Web UI Deploy Page" \
    "curl -sf -m 5 -I ${WEB_BASE}/deploy | head -1 | grep -q '200'"

echo "=== 5. Detailed API Response Tests ==="
echo ""

# Test config structure
echo "[$((test_count + 1))] Testing: Config Structure"
test_count=$((test_count + 1))
config_response=$(curl -sf -m 5 ${API_BASE}/api/config 2>&1)
if echo "$config_response" | jq -e '.channel_name, .primary_input, .backup_input, .output' > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC} - Config has required fields"
    pass_count=$((pass_count + 1))
    echo "    Channel: $(echo "$config_response" | jq -r '.channel_name')"
    echo "    Primary: $(echo "$config_response" | jq -r '.primary_input.url')"
    echo "    Backup: $(echo "$config_response" | jq -r '.backup_input.url')"
    echo "    Output: $(echo "$config_response" | jq -r '.output.url')"
else
    echo -e "${RED}FAIL${NC} - Config structure invalid"
    fail_count=$((fail_count + 1))
fi
echo ""

# Test smoke check structure
echo "[$((test_count + 1))] Testing: Smoke Check Structure"
test_count=$((test_count + 1))
smoke_response=$(curl -sf -m 5 ${API_BASE}/api/runtime/smoke 2>&1)
if echo "$smoke_response" | jq -e '.ok, .checks, .summary' > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC} - Smoke check has required fields"
    pass_count=$((pass_count + 1))
    echo "    Overall: $(echo "$smoke_response" | jq -r '.ok')"
    echo "    Pass: $(echo "$smoke_response" | jq -r '.summary.pass_count')"
    echo "    Warn: $(echo "$smoke_response" | jq -r '.summary.warn_count')"
    echo "    Fail: $(echo "$smoke_response" | jq -r '.summary.fail_count')"
    echo ""
    echo "    Checks:"
    echo "$smoke_response" | jq -r '.checks[] | "      - \(.name): \(.status)"'
else
    echo -e "${RED}FAIL${NC} - Smoke check structure invalid"
    fail_count=$((fail_count + 1))
fi
echo ""

# Test runtime status
echo "[$((test_count + 1))] Testing: Runtime Status Structure"
test_count=$((test_count + 1))
status_response=$(curl -sf -m 5 ${API_BASE}/api/runtime/status 2>&1)
if echo "$status_response" | jq -e '.active_source, .services' > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC} - Runtime status has required fields"
    pass_count=$((pass_count + 1))
    echo "    Active Source: $(echo "$status_response" | jq -r '.active_source')"
    echo "    Primary State: $(echo "$status_response" | jq -r '.primary_state')"
    echo "    Backup State: $(echo "$status_response" | jq -r '.backup_state')"
    echo "    Output State: $(echo "$status_response" | jq -r '.output_state')"
    echo ""
    echo "    Services:"
    echo "$status_response" | jq -r '.services[] | "      - \(.name): \(.status)"'
else
    echo -e "${RED}FAIL${NC} - Runtime status structure invalid"
    fail_count=$((fail_count + 1))
fi
echo ""

echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Total Tests: $test_count"
echo -e "Passed: ${GREEN}$pass_count${NC}"
echo -e "Failed: ${RED}$fail_count${NC}"
echo ""

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi

# Made with Bob
