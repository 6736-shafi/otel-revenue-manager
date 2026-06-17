# ARCHITECTURE.md

## ETL
Playwright scrapes `https://otel-hackathon-data-site.vercel.app` (paginated list → detail drill-in). Transform normalises to `reservation × stay_date` grain; revenue distributed per night. Load is idempotent via `ON CONFLICT (reservation_id, stay_date) DO UPDATE`. `load_manifest` row written on every run.

## Database
Postgres 16. Views: `vw_stay_night_base` (non-cancelled, Posted) and `vw_segment_stay_night` (+ effective macro group via lateral join on `market_macro_group_history`).

## Tool Layer (5 tools — no raw SQL exposed to model)

| Tool | View | Notes |
|------|------|-------|
| `get_otb_summary` | `vw_stay_night_base` | Monthly OTB: reservations, room nights, revenues, ADR |
| `get_segment_mix` | `vw_segment_stay_night` | Segment shares with macro group |
| `get_pickup_delta` | `reservations_hackathon` | Booking pace in Europe/London windows |
| `get_as_of_otb` | `reservations_hackathon` | **HITL-gated** point-in-time snapshot |
| `get_block_vs_transient_mix` | `vw_stay_night_base` | Group/block vs transient + top 3 companies |

## Deep Agents Wiring (create_deep_agent)

| Concept | Parameter | Implementation |
|---------|-----------|----------------|
| Tools | `tools=ALL_TOOLS` | 5 typed `@tool` functions |
| Skills | `skills=["skills_da/"]` | 7 SKILL.md files via FilesystemBackend; progressive disclosure |
| Subagents | `subagents=[SEGMENT_SUBAGENT]` | segment-analyst routes segment/block-mix queries |
| Planning | built-in TodoListMiddleware | `write_todos` decomposes multi-part questions |
| Memory | `memory=["memory/AGENTS.md"]` + `InMemorySaver` checkpointer | Persistent context + multi-turn state by thread_id |
| HITL | Native LangGraph `interrupt()` | Manual `interrupt()` call inside `get_as_of_otb` gates expensive point-in-time rebuild |
| Filesystem | `backend=FilesystemBackend(root_dir=…)` | Virtual FS for skill file reads |

## Skill → Tool Routing

| Skill | Tools | Key Judgment |
|-------|-------|-------------|
| `otb-health` | `get_otb_summary` | Occ < 60% = at-risk; ADR < £120 = low |
| `segment-analysis` | `get_segment_mix` | OTA > 50% = high risk; Corp < 15% = weak |
| `pickup-analysis` | `get_pickup_delta` | < 20 RN/week = slow; OTA > 70% of pickup = rate sensitive |
| `group-analysis` | `get_block_vs_transient_mix` | Block > 40% = displacement risk |
| `cancellation-risk` | `get_otb_summary`, `get_as_of_otb` (HITL) | Cancel rate > 25% = high risk |
| `room-type-mix` | `get_otb_summary` | Superior < 30% booked = upsell opportunity |
| `challenge-skill` | all | Master routing + morning briefing orchestration |

## Deployment
FastAPI backend (`:8000`) + Streamlit UI (`:8501`). HTTP Basic Auth on all endpoints. `GET /health` returns `db_fingerprint`, `dataset_revision`, `row_hash`, `financial_status_posted_only_rows`.
