# SUBMISSION.md

## Candidate
- Name: Shafi Uddin
- Submission Date: 2026-06-15

## Solution Repository URL
https://github.com/6736-shafi/otel-revenue-manager

## Live Agent URL
https://otel-revenue-manager-production.up.railway.app/

## Demo Video
https://www.youtube.com/watch?v=1R-JFIycf0s

## Basic Auth Credentials
- Username: `admin`
- Password: `revenue2025`

## Health Endpoint
GET https://otel-revenue-manager.railway.app/health

## Submission Checklist

### Phase 0 - Attestation
- [x] ATTESTATION.md completed with all 13 comprehension answers

### Phase 1 - ETL
- [x] Playwright scraper for client-rendered pages
- [x] Button-based pagination (not URL params)
- [x] Tab-based reference data scraping
- [x] Direct stay rows from detail pages (grain: reservation × stay_date)
- [x] Idempotent load via ON CONFLICT (reservation_id, stay_date) DO UPDATE
- [x] etl/SCRAPE_MANIFEST.json generated
- [x] etl/LOAD_PROOF.json generated
- [x] Tests: tests/test_etl.py (≥3 cases)

### Phase 2 - Tools
- [x] get_otb_summary(stay_month, exclude_cancelled)
- [x] get_segment_mix(stay_month, macro_group)
- [x] get_pickup_delta(booking_window_days, future_stay_from)
- [x] get_as_of_otb(stay_month, as_of_utc) — HITL gated
- [x] get_block_vs_transient_mix(stay_month)
- [x] Views: vw_stay_night_base, vw_segment_stay_night
- [x] tools/METRIC_DEFINITIONS.md
- [x] Tests: tests/test_tools.py (≥10 cases), tests/test_skills.py (≥5 cases), tests/test_agent.py (≥4 cases)

### Phase 3 - Skills and Architecture
- [x] skills/otb-health/SKILL.md (judgment: occ <60% = at-risk, ADR <£120 = low)
- [x] skills/segment-analysis/SKILL.md (judgment: OTA >50% = high risk)
- [x] skills/pickup-analysis/SKILL.md (judgment: 7-day pickup <20 RN = slow)
- [x] skills/group-analysis/SKILL.md (judgment: block >40% = displacement risk)
- [x] skills/cancellation-risk/SKILL.md (judgment: cancel rate >25% = high risk; HITL gate)
- [x] skills/room-type-mix/SKILL.md (judgment: Superior <30% booked = upsell opportunity)
- [x] skills/CHALLENGE_SKILL.md (version: otel-rm-v2, master routing + morning briefing)
- [x] ARCHITECTURE.md (≤1 page: skill→tool routing matrix, subagent + HITL documented)

### Phase 4 - Deploy
- [x] Streamlit chat UI (ui/app.py)
- [x] FastAPI backend (api/main.py)
- [x] /health endpoint
- [x] HTTP Basic Auth on all endpoints
- [x] LangGraph agent with tool streaming
- [x] Segment subagent for routing
- [x] HITL for get_as_of_otb

## Architecture Summary
- Database: PostgreSQL 16 (Docker locally, Railway for production)
- Backend: FastAPI + LangGraph agent
- UI: Streamlit with tool call visibility
- Agent: DeepSeek (main) + Claude Sonnet 4.6 (segment subagent)
- ETL: Playwright + psycopg2 (batch scrape, idempotent load)
