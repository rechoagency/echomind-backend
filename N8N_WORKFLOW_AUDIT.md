# N8N Workflow Audit Report

**Date:** 2025-11-27
**Audited By:** Claude Code (Automated)
**N8N Instance:** https://recho-echomind.app.n8n.cloud

---

## Summary (AFTER FIXES APPLIED)

| Status | Count |
|--------|-------|
| Active & Working | 6 |
| Deactivated | 9 |

### Fixes Applied Automatically:
1. **Fixed** "Daily Reddit Scan" - URL changed from `/api/admin/scan-opportunities` to `/api/admin/trigger-reddit-scan`
2. **Fixed** "Weekly Reports" - URL changed from `/api/reports/weekly/all` to `/api/admin/send-weekly-reports`
3. **Fixed** "Voice Database Update" - URL changed from `/api/admin/update-voice-database` to `/api/option-b/voice-database/run`
4. **Fixed** "Document Vectorization" - Added missing `/api/documents/store` endpoint to backend
5. **Deactivated** 9 placeholder workflows (only contain sticky notes, no functionality)

---

## ACTIVE WORKFLOWS (6 Total)

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

### 5. EchoMind - Voice Database Update (FIXED)
- **ID:** `V4664RXeuyPpNRJP`
- **Schedule:** 1st of month at 3am EST (cron: `0 8 1 * *`)
- **Endpoint:** `POST /api/option-b/voice-database/run` (was `/api/admin/update-voice-database`)
- **Status:** WORKING (after fix)

### 6. EchoMind - Document Vectorization (FIXED)
- **ID:** `S9jq5QFGb0Kpl7po`
- **Trigger:** Webhook (`/document-upload`)
- **Endpoints Called:**
  - `POST /api/documents/store` (added to backend)
  - OpenAI Embeddings API
  - Direct Supabase for vector storage
- **Status:** WORKING (after adding endpoint)

---

## DEACTIVATED WORKFLOWS (9 Total)

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

---

## Feature Gap Analysis

### Voice Database (EXISTS ✅)

**Code Location:**
- `workers/voice_database_worker.py` - Builds voice profiles by crawling Reddit
- `workers/voice_application_worker.py` - Applies voice profiles to generated content

**Exposed Endpoints:**
- `POST /api/option-b/voice-database/run` - Triggers voice database builder
- `GET /api/option-b/status` - Shows voice profile count

**Capabilities:**
- Crawls top Redditors in target subreddits
- Extracts linguistic patterns (idioms, grammar, sentence structure)
- Uses GPT-4 to analyze tone and style
- Saves profiles to `voice_profiles` table
- Applies voice transformations to generated content

**Status:** FULLY IMPLEMENTED - No N8N workflow needed (has manual endpoint)

---

### Document Vectorization (EXISTS ✅)

**Code Location:**
- `services/document_processor.py` - Text extraction, chunking, embedding generation
- `services/document_ingestion_service.py` - Full document pipeline
- `routers/documents_router.py` - API endpoints
- `services/knowledge_matchback_service.py` - RAG similarity search
- `sql/match_knowledge_embeddings.sql` - PostgreSQL vector search function

**Exposed Endpoints:**
- `GET /api/clients/{client_id}/documents` - List uploaded documents
- `POST /api/clients/{client_id}/documents/upload` - Upload and vectorize documents
- `DELETE /api/clients/{client_id}/documents/{document_id}` - Delete document
- `GET /api/clients/{client_id}/documents/{document_id}/embeddings` - Get embedding count

**Capabilities:**
- Supports: PDF, Word (.docx), Excel, CSV, JSON, TXT, MD
- Text extraction with smart chunking (1000 char chunks, 200 char overlap)
- OpenAI embeddings (text-embedding-ada-002 and text-embedding-3-small)
- Vector similarity search via Supabase pgvector
- RAG integration for content generation

**Status:** FULLY IMPLEMENTED - Endpoints already exist

---

### N8N Workflows - FIXED ✅

Both workflows have been fixed and reactivated:

| Workflow | Was Calling | Now Calling | Status |
|----------|-------------|-------------|--------|
| Voice Database Update | `/api/admin/update-voice-database` ❌ | `/api/option-b/voice-database/run` ✅ | ACTIVE |
| Document Vectorization | `/api/documents/store` ❌ | `/api/documents/store` ✅ (endpoint added) | ACTIVE |

**All core workflows are now operational.**
