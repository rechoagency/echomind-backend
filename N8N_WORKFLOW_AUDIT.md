# N8N Workflow Audit Report

**Date:** 2025-11-27
**Audited By:** Claude Code (Automated)
**N8N Instance:** https://recho-echomind.app.n8n.cloud

---

## Summary (AFTER FIXES APPLIED)

| Status | Count |
|--------|-------|
| Active & Working | 4 |
| Deactivated | 11 |

### Fixes Applied Automatically:
1. **Fixed** "Daily Reddit Scan" - URL changed from `/api/admin/scan-opportunities` to `/api/admin/trigger-reddit-scan`
2. **Fixed** "Weekly Reports" - URL changed from `/api/reports/weekly/all` to `/api/admin/send-weekly-reports`
3. **Deactivated** 2 broken workflows (endpoints don't exist in backend)
4. **Deactivated** 9 placeholder workflows (only contain sticky notes, no functionality)

---

## ACTIVE WORKFLOWS (4 Total)

### 1. EchoMind - Brand Monitoring
- **ID:** `xjihOZiqKdym4PVV`
- **Schedule:** Every 15 minutes
- **Endpoint:** `POST /api/admin/trigger-reddit-scan`
- **Status:** WORKING
- **Verified:** 436+ opportunities in database

### 2. EchoMind - Daily Reddit Scan (FIXED)
- **ID:** `0WTDaHfr8WLMcNJx`
- **Schedule:** Daily at 9am EST (cron: `0 14 * * *`)
- **Endpoint:** `POST /api/admin/trigger-reddit-scan` (was `/api/admin/scan-opportunities`)
- **Status:** WORKING (after fix)

### 3. EchoMind - Weekly Reports (FIXED)
- **ID:** `XkqZxe7gWI6oIHrq`
- **Schedule:** Mon/Thu 7am EST (cron: `0 12 * * 1,4`)
- **Endpoint:** `POST /api/admin/send-weekly-reports` (was `/api/reports/weekly/all`)
- **Status:** WORKING (after fix)

### 4. EchoMind - Client Onboarding
- **ID:** `MZknp04E5W3yq8bP`
- **Trigger:** Webhook (`/client-onboarding`)
- **Endpoints Called:**
  - `POST /api/admin/trigger-orchestrator/{client_id}`
  - `POST /api/admin/regenerate-reports/{client_id}`
- **Status:** WORKING

---

## DEACTIVATED WORKFLOWS (11 Total)

### Broken Workflows (Endpoints Don't Exist)

| Workflow | ID | Issue |
|----------|-----|-------|
| EchoMind - Voice Database Update | V4664RXeuyPpNRJP | `/api/admin/update-voice-database` doesn't exist |
| EchoMind - Document Vectorization | S9jq5QFGb0Kpl7po | `/api/documents/store` doesn't exist |

### Placeholder Workflows (Not Implemented - Only Sticky Notes)

| Workflow | ID |
|----------|-----|
| Workflow 7: Voice Database Crawler | X6B5ppHNzWkrgJd9 |
| Workflow 8: RAG Content Generator | s0UBidzjJeeJhJcf |
| Workflow 9: Self-Monitoring & Health Checks | gGJUOBjkXng33hD6 |
| Workflow 10: Multi-Tenancy Team Manager | Dnep1ocxmSf7fQjD |
| Workflow 11: Google API Integration | TbVEaW18Egw8dScZ |
| Workflow 12: Reddit Pro Answers Integration | bUb5VKS1rJXAtD7c |
| Workflow 13: Real-Time Auto-Reply | 3zkeiq8AevQjoan6 |
| Workflow 14: Intelligence Report Generator | nYoKZjgD3s2ytX5O |
| Workflow 15: Auto-Audit Self-Healing | lOVSOCVoxjB41gGy |

---

## Backend Endpoints Reference

| Purpose | Endpoint | Method |
|---------|----------|--------|
| Trigger Reddit scan | `/api/admin/trigger-reddit-scan` | POST |
| Send weekly reports (all) | `/api/admin/send-weekly-reports` | POST |
| Send weekly report (one client) | `/api/admin/send-weekly-report/{client_id}` | POST |
| Trigger orchestrator | `/api/admin/trigger-orchestrator/{client_id}` | POST |
| Regenerate reports | `/api/admin/regenerate-reports/{client_id}` | POST |
| Run worker pipeline | `/api/admin/run-worker-pipeline` | POST |
| Health check | `/health` | GET |

---

## Note on Redundancy

Both "Brand Monitoring" (every 15 min) and "Daily Reddit Scan" (daily 9am) now call the same endpoint. This is intentional redundancy:
- **Brand Monitoring** provides frequent updates
- **Daily Reddit Scan** is a backup/catch-up scan

You may choose to deactivate one if redundancy is not needed.

---

## N8N API Access

For future audits:
```bash
curl "https://recho-echomind.app.n8n.cloud/api/v1/workflows" \
  -H "X-N8N-API-KEY: <your-api-key>"
```
