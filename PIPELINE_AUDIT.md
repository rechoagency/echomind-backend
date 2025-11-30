# Content Generation Pipeline Audit

**Date:** 2025-11-30
**Auditor:** Claude Code
**Last Updated:** 2025-11-30 05:15 UTC

---

## Executive Summary

| Component | EXISTS | CONNECTED | ACTUALLY RUNNING | DATA POPULATED |
|-----------|--------|-----------|------------------|----------------|
| **1. Grading System** | YES | YES | FIXED (endpoint added) | Logging only (schema needs columns) |
| **2. Voice Database** | YES | YES | NO (never run) | 0 voice profiles |
| **3. Knowledge RAG** | YES | YES | YES (but empty) | 0 documents/chunks |
| **4. GPT Humanization** | YES | YES | **YES - WORKING** | **4 pieces generated!** |

**Bottom Line:** Content generation is NOW WORKING! Generated 4 pieces of content for Mira. The infrastructure is complete - remaining gap is **data population** for voice profiles and knowledge base.

---

## RECENT FIXES (2025-11-30)

### Content Generation - FIXED ✅
- Fixed column name mismatches (`original_post_text` not `thread_content`)
- Fixed `content_delivered` insert (correct column names)
- Fixed dead code bug (service initialization after `raise`)
- **Result:** 4 pieces of content generated and stored

### Opportunity Scoring - PARTIAL FIX ⚠️
- Added `POST /api/admin/run-opportunity-scoring` endpoint
- Fixed column name (`original_post_text` instead of `thread_content`)
- DB update disabled (scoring columns don't exist in schema)
- Scores are logged but not persisted

### New Admin Endpoints Added
- `POST /api/admin/run-opportunity-scoring` - Manual trigger for scoring
- `GET /api/admin/pipeline-status` - Check all pipeline component status
- `POST /api/admin/test-content-generation` - Synchronous test endpoint

### Current Pipeline Status (from `/api/admin/pipeline-status`):
```json
{
  "voice_database": {"profiles": 0, "status": "EMPTY"},
  "opportunity_scoring": {"scored": 0, "total": 96283, "status": "NOT_RUN"},
  "knowledge_base": {"documents": 0, "embeddings": 0, "status": "EMPTY"},
  "content_generation": {"pieces": 4, "status": "ACTIVE"}
}
```

---

---

## 1. GRADING SYSTEM

### File: `workers/opportunity_scoring_worker.py`

**EXISTS:** YES (406 lines)

**Scoring Formula (weights):**
```
opportunity_score = (
    buying_intent_score * 0.35 +   # 35% - Buying keywords
    pain_point_score * 0.25 +       # 25% - Pain/frustration words
    question_score * 0.20 +         # 20% - Questions = seeking advice
    engagement_score * 0.10 +       # 10% - Comment count
    urgency_score * 0.10            # 10% - Urgency words
)
```

**Priority Tiers:**
- URGENT: score >= 90
- HIGH: score >= 75
- MEDIUM: score >= 60
- LOW: score < 60

**Buying Intent Keywords (Line 29-35):**
- HIGH (10pts): buy, purchase, recommend, worth it, price, cost, budget
- MEDIUM (5pts): help, advice, suggest, tips, how to
- LOW (2pts): thinking about, considering, maybe

**Pain Point Keywords (Line 38-42):**
- struggling, problem, frustrated, terrible, can't stand, doesn't work

**CONNECTED to Content Generation:** YES
- Scheduler calls `opportunity_scorer.process_all_opportunities()` as Step 1
- Content generation queries `opportunity_score` column to prioritize

**ACTUALLY RUNNING:** NO
- Not scheduled in main.py APScheduler
- N8N workflow exists but unclear if triggered
- Evidence: 0 opportunities have `opportunity_score` populated

**HOW TO FIX:**
1. Add to main.py scheduler (after Reddit scan)
2. OR trigger via N8N after daily scan
3. OR add API endpoint to trigger manually

---

## 2. VOICE DATABASE

### Files:
- `workers/voice_database_worker.py` (313 lines) - Builds profiles
- `workers/voice_application_worker.py` (410 lines) - Applies profiles

### Voice Database Worker (Building Profiles)

**EXISTS:** YES

**What It Analyzes (Line 133-179):**
- avg_sentence_length
- avg_word_length
- common_phrases (bigrams/trigrams)
- typo_frequency
- uses_emojis (frequent/occasional/rare)
- exclamation_frequency
- question_frequency

**GPT-4 Enhancement (Line 181-226):**
- tone (3-5 words)
- grammar_style
- sentiment_distribution
- signature_idioms (5-10 phrases)
- formality_level (LOW/MEDIUM/HIGH)
- voice_description (2 sentences)

**CONNECTED to Content Generation:** YES
- `get_voice_profile()` called in `generate_content_for_client()` (Line 383)
- Voice metrics added to GPT prompt (Lines 210-221)

**ACTUALLY RUNNING:** NO
- N8N workflow "Voice Database Update" scheduled for 1st of month
- Evidence from API: `"voice_profiles": 0`
- Worker has never been run

### Voice Application Worker (Post-Processing)

**EXISTS:** YES

**What It Applies (Line 188-224):**
- Lowercase style adjustment
- Exclamation usage adjustment
- Formality level (contractions vs formal language)
- Tone markers

**CONNECTED to Content Generation:** YES
- Scheduler calls `voice_application.process_all_content()` as Step 4
- But it processes `generated_content` table (not `content_delivered`)

**ACTUALLY RUNNING:** NO
- Queries `generated_content` table which doesn't exist
- Content is stored in `content_delivered` table instead

### Why 0 Voice Profiles?

1. Voice Database Worker has NEVER been triggered
2. Requires Reddit API crawling (PRAW) which needs:
   - `REDDIT_CLIENT_ID`
   - `REDDIT_CLIENT_SECRET`
   - `REDDIT_USER_AGENT`
3. N8N scheduled for 1st of month - may not have fired yet

**HOW TO FIX:**
```bash
# Trigger voice database build manually
curl -X POST "https://echomind-backend-production.up.railway.app/api/option-b/voice-database/run"
```
Or wait until 1st of next month when N8N triggers it.

---

## 3. CLIENT VECTORIZED DATABASE (Knowledge RAG)

### File: `services/knowledge_matchback_service.py`

**EXISTS:** YES (234 lines)

**How RAG Works:**
1. Generate embedding for opportunity text (Line 62)
2. Vector search via Supabase RPC `match_knowledge_embeddings` (Line 74-82)
3. Return relevant insights with similarity scores (Line 88-103)

**Uses Tables:**
- `client_documents` - Uploaded documents
- `document_embeddings` - Vectorized chunks

**CONNECTED to Content Generation:** YES (Lines 388-397 in content_generation_worker.py)
```python
knowledge_insights = self.knowledge_matchback.match_opportunity_to_knowledge(
    opportunity_text=opportunity_text,
    client_id=client_id,
    similarity_threshold=0.70,
    max_insights=3
)
```

**Added to GPT Prompt:** YES (Lines 224-247)
```
**UNIQUE DATA & RESEARCH (from your company's knowledge base):**
You have access to proprietary research, case studies, and data...
```

**ACTUALLY RUNNING:** YES (code executes)

**BUT NO DATA:**
```json
{
  "documents_uploaded": 0,
  "knowledge_chunks": 0
}
```

**Why 0 Documents?**
1. No client has uploaded documents
2. Document upload endpoint exists: `POST /api/documents/store`
3. N8N "Document Vectorization" workflow exists but no data to process

**HOW TO FIX:**
1. Upload documents for Mira client via API or dashboard
2. Documents will be chunked and embedded automatically
3. RAG will then return relevant insights during content generation

---

## 4. GPT-4 HUMANIZATION

### File: `workers/content_generation_worker.py` - `build_generation_prompt()`

**EXISTS:** YES (Lines 148-296)

### Prompt Structure:

**1. Thread Context:** YES
```
**Thread Title:** {thread_title}
**Thread Content:** {thread_content}
```

**2. Voice Profile Parameters:** YES (Lines 210-221)
```
**Community Voice Style (r/{subreddit}):**
- Formality: Casual and conversational / Moderately formal / Professional
- Tone: {dominant_tone}
- Writing style: Often starts lowercase, relaxed / Standard capitalization
- Enthusiasm: High energy / Moderate / Calm and measured
```

**3. Knowledge Base Insights:** YES (Lines 224-247)
```
**UNIQUE DATA & RESEARCH (from your company's knowledge base):**
1. **Insight from {source}** (relevance: {relevance}%):
   {excerpt}
```

**4. Anti-AI Pattern Instructions:** YES (Lines 284-293)
```
- BE AUTHENTIC: Sound like a real person sharing experience, not an ad
- BE HELPFUL FIRST: Address their problem genuinely
- BE SUBTLE: do it naturally ("I've had good results with...")
- BE HONEST: Add disclaimers like "not sponsored"
- MATCH THE TONE: Use the community's voice style
- BE BRIEF: 2-4 sentences max
```

**5. Brand/Product Mention Control:** YES
- Uses `mention_brand` boolean from slider settings
- Uses `mention_product` boolean from similarity threshold

**6. Special Instructions:** YES (Lines 259-267)
```
**CRITICAL COMPLIANCE GUIDELINES (MUST FOLLOW):**
{explicit_instructions}
```

**ACTUALLY RUNNING:** YES
- Evidence: Content generated for Mira shows:
  - Medical disclaimer included (from special instructions)
  - Empathetic tone maintained
  - 2-4 sentences length
  - No hard selling

---

## Component Connection Diagram

```
+-------------------+     +--------------------+     +---------------------+
|  Reddit Scanner   | --> | Opportunity Scorer | --> | Product Matchback   |
| (N8N Daily 9am)   |     | (NOT SCHEDULED!)   |     | (Works but 0 prods) |
+-------------------+     +--------------------+     +---------------------+
                                    |                         |
                                    v                         v
                          +--------------------+     +---------------------+
                          |   Voice Database   |     | Knowledge Matchback |
                          |   (0 profiles!)    |     |   (0 documents!)    |
                          +--------------------+     +---------------------+
                                    |                         |
                                    v                         v
                          +------------------------------------------+
                          |         CONTENT GENERATION WORKER         |
                          | - Gets voice profile (returns None)       |
                          | - Gets knowledge insights (returns [])    |
                          | - Builds GPT prompt                       |
                          | - Generates content                       |
                          +------------------------------------------+
                                            |
                                            v
                          +------------------------------------------+
                          |         VOICE APPLICATION WORKER          |
                          | - Post-processes text (WRONG TABLE!)      |
                          +------------------------------------------+
```

---

## Priority Fix List

### CRITICAL (Blocks Core Functionality)

| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| 1 | **Voice database empty** | Content lacks subreddit-specific voice | Run `POST /api/option-b/voice-database/run` |
| 2 | **Opportunity scoring not running** | Opportunities not prioritized | Add to main.py scheduler |
| 3 | **Knowledge base empty** | No RAG insights in content | Upload documents for clients |

### HIGH (Degrades Quality)

| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| 4 | Voice Application uses wrong table | Voice post-processing never runs | Change from `generated_content` to `content_delivered` |
| 5 | No products configured | Product mentions impossible | Upload products for clients |

### MEDIUM (Nice to Have)

| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| 6 | Scoring columns may not exist | Scoring updates fail silently | Add columns to opportunities table |

---

## Immediate Actions

### 1. Build Voice Database NOW
```bash
curl -X POST "https://echomind-backend-production.up.railway.app/api/option-b/voice-database/run"
```

### 2. Upload Knowledge Documents for Mira
- Use document upload API or dashboard
- Upload: Product guides, FAQs, research papers

### 3. Schedule Opportunity Scoring
Add to `main.py`:
```python
scheduler.add_job(
    score_all_opportunities,
    trigger='cron',
    hour=10,  # After 9am Reddit scan
    minute=0
)
```

### 4. Fix Voice Application Worker
Change table from `generated_content` to `content_delivered`

---

## Summary (Updated 2025-11-30)

**What's Working:**
- Content generation produces content (**4 pieces generated!**)
- GPT prompt includes all components (when data exists)
- Database insert fixed (`content_delivered` table)
- Content appears in dashboard
- New admin endpoints for debugging

**What's Partially Fixed:**
- Opportunity scoring: Code fixed, but scoring columns don't exist in schema
- Endpoint added: `POST /api/admin/run-opportunity-scoring`

**What Still Needs Work:**
- Voice profiles: 0 (never built) - needs `POST /api/option-b/voice-database/run`
- Knowledge base: 0 documents (never uploaded)
- Voice post-processing: Uses wrong table

**Remaining Critical Path:**
1. Run voice database builder
2. Upload knowledge documents for clients
3. Add scoring columns to opportunities table OR use score in-memory
4. Fix voice application table reference

**The core content generation pipeline is NOW FUNCTIONAL.** Content is being generated and stored. Remaining work is data population and schema updates.
