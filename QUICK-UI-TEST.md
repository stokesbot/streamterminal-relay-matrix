# Quick UI Testing Guide

This guide helps you quickly test all UI components on your VPS (46.225.116.163).

**Reference:** See [`docs/operations.md`](docs/operations.md) for detailed operational procedures.

---

## Quick Start

### 1. Run Diagnostic Script on VPS

```bash
# SSH into VPS
ssh root@46.225.116.163

# Run the diagnostic script
cd /path/to/streamterminal-relay-matrix
chmod +x vps-diagnostic-report.sh
./vps-diagnostic-report.sh
```

This will show you:
- Service status (API, Web UI, MediaMTX, Relay)
- Port listening status
- API health checks
- Current configuration
- Recent logs

---

## 2. Test UI Pages in Browser

Open these URLs in your browser:

1. **Dashboard:** `http://46.225.116.163:3000/`
2. **Configuration:** `http://46.225.116.163:3000/config`
3. **Diagnostics:** `http://46.225.116.163:3000/diagnostics`
4. **Deployment:** `http://46.225.116.163:3000/deploy`

---

## 3. Quick Component Tests

### Dashboard (`/`)

**What to check:**
- [ ] Status pills show current state (primary/backup/output)
- [ ] "Run smoke" button works and shows results
- [ ] Service status cards display correctly
- [ ] "Logs" buttons show service logs
- [ ] Live smoke section shows 6 checks with pass/fail status

**Quick test:**
1. Click "Run smoke" button
2. Verify smoke results appear with green/red status indicators
3. Click "Logs" on MediaMTX service
4. Verify logs appear below the service card

### Configuration (`/config`)

**What to check:**
- [ ] Form shows current primary/backup/output URLs
- [ ] "Validate draft" button works
- [ ] "Save draft" button saves changes
- [ ] Validation results appear with color-coded severity

**Quick test:**
1. Change the channel name
2. Click "Save draft"
3. Click "Validate draft"
4. Verify validation results appear

### Diagnostics (`/diagnostics`)

**What to check:**
- [ ] Generated artifacts preview (MediaMTX config, systemd units)
- [ ] Host tools status (all should show "available")
- [ ] Latest revision information

**Quick test:**
1. Scroll through artifact previews
2. Verify all host tools show green "available" status
3. Check latest revision matches your last apply

### Deployment (`/deploy`)

**What to check:**
- [ ] Preflight checks show pass/fail status
- [ ] Deployment plan shows rollout steps
- [ ] Host snapshots are listed
- [ ] Bundle inventory shows bundle count and sizes

**Quick test:**
1. Scroll to "Preflight checks" section
2. Verify all checks show current status
3. Check "Host snapshots" section for captured snapshots
4. Review "Bundle inventory" for bundle rotation info

---

## 4. API Endpoint Tests (Run on VPS)

Based on [`docs/operations.md`](docs/operations.md#10-api-endpoints), test these key endpoints:

```bash
# Health check
curl http://localhost:8000/api/health

# Smoke test (6 checks)
curl http://localhost:8000/api/runtime/smoke | jq '.summary'

# Runtime status
curl http://localhost:8000/api/runtime/status | jq '{active_source, primary_state, backup_state, output_state}'

# Current config
curl http://localhost:8000/api/config | jq '{channel_name, primary_input: .primary_input.url, backup_input: .backup_input.url, output: .output.url}'

# Preflight checks
curl 'http://localhost:8000/api/deploy/preflight?profile_id=local-system' | jq '.checks[] | {name, status}'

# Host snapshots
curl http://localhost:8000/api/deploy/host-snapshots | jq '.snapshots[] | {id, created_at, file_count}'
```

---

## 5. Common Issues & Fixes

### Issue: UI not loading
```bash
# Check if Next.js is running
ps aux | grep next

# Check port 3000
ss -tlnp | grep 3000

# If not running, start it
cd apps/web
npm run dev -- --hostname 0.0.0.0 --port 3000
```

### Issue: API calls failing
```bash
# Check if FastAPI is running
ps aux | grep uvicorn

# Check port 8000
ss -tlnp | grep 8000

# If not running, start it
cd apps/api
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Issue: CORS errors in browser console
Check `apps/api/app/config.py` - ensure `allowed_origins` includes your VPS IP:
```python
allowed_origins: list[str] = ["http://localhost:3000", "http://46.225.116.163:3000"]
```

### Issue: Smoke test failing
See [`docs/operations.md#4-when-a-publisher-cant-connect`](docs/operations.md#4-when-a-publisher-cant-connect) for troubleshooting steps.

---

## 6. Failover Testing

You mentioned failover works with RTMP (live/main, live/backup). To verify UI updates:

1. **Start with both streams active**
   - Dashboard should show "Active source: primary"
   - Primary state: healthy
   - Backup state: healthy

2. **Stop primary stream**
   - Wait 5-10 seconds
   - Dashboard should update to "Active source: backup"
   - Primary state: down
   - Backup state: healthy

3. **Restart primary stream**
   - Wait for reconnection
   - Dashboard should switch back to "Active source: primary"

4. **Check event log**
   - Recent events section should show failover events

---

## 7. Next Steps for SRT/H.265 Testing

### SRT Testing Plan
1. Update config with SRT URLs
2. Change protocol dropdown to "srt"
3. Set mode to "caller" or "listener" as appropriate
4. Apply config
5. Run smoke test
6. Verify failover works with SRT

### H.265 Testing Plan
1. Configure encoder to output H.265
2. Test with current RTMP setup
3. Monitor MediaMTX logs for codec warnings
4. Check if relay handles H.265 passthrough
5. Verify output stream quality

---

## 8. Browser DevTools Checklist

Open browser DevTools (F12) and check:

### Console Tab
- [ ] No JavaScript errors
- [ ] No React warnings
- [ ] API calls completing successfully

### Network Tab
- [ ] All API requests returning 200 status
- [ ] No CORS errors
- [ ] Response times are reasonable (<1s)

### Application Tab
- [ ] No localStorage errors
- [ ] Session storage working if used

---

## Report Template

After testing, document what you find:

```
## UI Test Results - [Date]

### Environment
- VPS: 46.225.116.163
- API: [✓ Running / ✗ Not Running]
- Web UI: [✓ Running / ✗ Not Running]
- Browser: [Chrome/Firefox/etc.]

### Working Components
- Dashboard status pills: [✓/✗]
- Smoke test button: [✓/✗]
- Service logs: [✓/✗]
- Config form: [✓/✗]
- Deployment preflight: [✓/✗]

### Issues Found
1. [Describe issue]
   - Steps to reproduce:
   - Expected behavior:
   - Actual behavior:
   - Browser console errors:

### Failover Test Results
- Primary → Backup switch time: [X seconds]
- UI updated correctly: [✓/✗]
- Event logged: [✓/✗]

### Next Actions
1. [Action item]
2. [Action item]
```

---

## Quick Reference Links

- **Operations Runbook:** [`docs/operations.md`](docs/operations.md)
- **Architecture:** [`docs/architecture.md`](docs/architecture.md)
- **MVP Plan:** [`docs/mvp-plan.md`](docs/mvp-plan.md)
- **API Endpoints:** [`docs/operations.md#10-api-endpoints`](docs/operations.md#10-api-endpoints)
- **Troubleshooting:** [`docs/operations.md#11-troubleshooting-matrix`](docs/operations.md#11-troubleshooting-matrix)