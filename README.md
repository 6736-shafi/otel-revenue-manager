# Hotel Revenue Manager Agent

A LangChain Deep Agent that answers hotel revenue management questions by querying a live PostgreSQL database populated by a Playwright ETL pipeline.

Built for the [otel.ai build challenge](https://github.com/otel-ai/otel-build-challenge).

---

## What it does

The agent answers GM-level revenue questions in plain English:

- *"What revenue is on the books for July?"*
- *"Are we too dependent on OTA?"*
- *"What changed in the last 7 days?"*
- *"How much group business do we have?"*
- *"Give me the morning briefing"*

It streams tool calls and skill loads live in the UI so you can see exactly what it ran.

---

## Stack

| Layer | Technology |
|---|---|
| Agent | LangChain `create_deep_agent` (deepagents 0.6.10) |
| Planning | `TodoListMiddleware` (built-in) |
| Memory | `MemoryMiddleware` + `InMemorySaver` checkpointer |
| Skills | `FilesystemMiddleware` + `FilesystemBackend` (7 SKILL.md files) |
| HITL | `HumanInTheLoopMiddleware` on `get_as_of_otb` |
| Subagent | `SubAgent` (segment-analyst) |
| Backend | FastAPI |
| UI | Streamlit (streams tool/skill events) |
| Database | PostgreSQL 16 |
| ETL | Playwright + psycopg2 |

---

## Quick start

### 1. Clone and create virtualenv

```bash
git clone https://github.com/shafiuddin/otel-revenue-manager
cd otel-revenue-manager
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env   # then edit .env
```

Required variables:

```env
DATABASE_URL=postgresql://hackathon:hackathon@localhost:5433/hotel_hackathon
LLM_PROVIDER=deepseek           # or anthropic / openai / groq / github
DEEPSEEK_API_KEY=sk-...         # recommended — full deepagents stack with HITL
ANTHROPIC_API_KEY=sk-ant-...    # full deepagents stack
GROQ_API_KEY=gsk_...            # free tier — lightweight ReAct fallback
GITHUB_TOKEN=ghp_...            # GitHub Models (GPT-4o via Azure)
APP_USERNAME=admin
APP_PASSWORD=revenue2025
SECRET_KEY=your-secret-key
```

### 3. Start the database

```bash
docker compose up -d
```

This starts Postgres on port 5433.

### 4. Run ETL

```bash
python etl/run_etl.py
```

Scrapes the live data site with Playwright, transforms to `reservation × stay_date` grain, loads idempotently. Generates `etl/SCRAPE_MANIFEST.json` and `etl/LOAD_PROOF.json`.

### 5. Run tests

```bash
python -m pytest tests/ -v
```

78 tests covering ETL, tools, skills, and agent graph structure.

### 6. Start the app

```bash
# Terminal 1 — API
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — UI
streamlit run ui/app.py --server.port 8501
```

Open [http://localhost:8501](http://localhost:8501). Login: `admin` / `revenue2025`.

---

## Agent building blocks

All five required Deep Agent concepts are wired in `agent/revenue_agent.py` via a single `create_deep_agent()` call:

```python
create_deep_agent(
    model=llm,
    tools=ALL_TOOLS,                        # 5 typed tool functions
    system_prompt=SYSTEM_PROMPT,
    skills=["skills/"],                     # 7 SKILL.md files, loaded on demand
    memory=["memory/AGENTS.md"],            # persistent GM context
    subagents=[SEGMENT_SUBAGENT],           # segment-analyst SubAgent
    interrupt_on={"get_as_of_otb": True},   # HITL gate
    backend=FilesystemBackend(root_dir=..., virtual_mode=True),
    checkpointer=InMemorySaver(),
)
```

| Concept | Implementation |
|---|---|
| Tools | `get_otb_summary`, `get_segment_mix`, `get_pickup_delta`, `get_as_of_otb`, `get_block_vs_transient_mix` |
| Skills | 7 SKILL.md files in `skills/` — encode revenue judgment thresholds |
| Subagents | `segment-analyst` SubAgent for segment/block-mix routing |
| Planning | `TodoListMiddleware` decomposes multi-part questions via `write_todos` |
| Memory | `MemoryMiddleware` + `InMemorySaver` checkpointer by `thread_id` |
| Filesystem | `FilesystemBackend` for virtual skill file reads |
| HITL | `HumanInTheLoopMiddleware` gates `get_as_of_otb` behind approval |

---

## Tools

| Tool | View | Purpose |
|---|---|---|
| `get_otb_summary` | `vw_stay_night_base` | Monthly OTB: reservations, room nights, ADR, revenue |
| `get_segment_mix` | `vw_segment_stay_night` | Segment shares with effective macro group |
| `get_pickup_delta` | `reservations_hackathon` | 7/14/30-day booking pace (Europe/London timezone) |
| `get_as_of_otb` | `reservations_hackathon` | **HITL-gated** point-in-time OTB snapshot |
| `get_block_vs_transient_mix` | `vw_stay_night_base` | Group vs transient split + top 3 companies |

---

## Skills

Seven skills in `skills/` encode revenue manager judgment — not just metric definitions, but thresholds and recommended actions:

| Skill | Key Judgment |
|---|---|
| `challenge-skill` | Master routing + morning briefing orchestration (`otel-rm-v2`) |
| `otb-health` | Occ < 60% = at-risk; ADR < £120 = under-priced |
| `segment-analysis` | OTA > 50% = high dependency risk |
| `pickup-analysis` | < 20 RN/week = slow demand; act now |
| `group-analysis` | Block > 40% = displacement risk |
| `cancellation-risk` | OTA > 50% + cancel rate > 25% = high exposure; HITL on `get_as_of_otb` |
| `room-type-mix` | Superior < 30% booked = upsell opportunity |

---

## Health endpoint

```bash
curl -u admin:revenue2025 https://<your-host>/health
```

```json
{
  "db_fingerprint": "a458a75f...",
  "dataset_revision": "2026-06-15",
  "row_hash": "a458a75f...",
  "financial_status_posted_only_rows": 466
}
```

---

## Repository structure

```
agent/          revenue_agent.py — create_deep_agent() wiring
api/            FastAPI backend, /health, /chat endpoints
etl/            scraper.py, transform.py, load.py, run_etl.py
                SCRAPE_MANIFEST.json, LOAD_PROOF.json
memory/         AGENTS.md — persistent GM context
scripts/        compute_load_fingerprint.py
skills/         7 SKILL.md files (skills/challenge-skill/SKILL.md etc.)
                CHALLENGE_SKILL.md (otel-rm-v2 flat file)
sql/            VIEWS.example.sql
tests/          test_etl.py, test_tools.py, test_skills.py, test_agent.py
tools/          revenue_tools.py, METRIC_DEFINITIONS.md
ui/             app.py — Streamlit chat + direct query dashboard
ARCHITECTURE.md skill→tool routing matrix, deepagents wiring
ATTESTATION.md  Phase 0 comprehension (13 answers)
SUBMISSION.md   Live URL, credentials pointer, checklist
schema.sql      Postgres table definitions
```

---

## Future enhancements

This challenge implements one hotel's revenue picture. The architecture is designed to extend — here is where it goes next.

### 1. Rate recommendation engine

The agent currently *describes* the situation. The next layer is *prescribing* specific actions: "Raise BAR by £15 for the 14-day window — OTA pickup is accelerating and you're 68% occupied." This requires adding a `suggest_rate_action` tool that combines OTB, pickup pace, and competitor context, then encodes a yield curve into a new skill. The judgment stays in code; the model communicates it.

### 2. Multi-property portfolio view

A single-hotel agent is a proof case. A GM running three properties needs a portfolio skill that fans out across property-scoped tool calls, aggregates risk signals, and surfaces the property that needs attention first. The subagent pattern already handles routing — extending it to `PropertySubAgent` per site is the natural step. Each property gets its own DB schema (or schema namespace) and its own skill pack. The orchestrator agent reasons across them.

### 3. Proactive briefings and anomaly alerts

Right now the agent is reactive — the GM asks, it answers. The next layer is scheduled proactive events: a morning briefing pushed at 07:00 London time when pickup drops below threshold, a cancellation spike alert when a block cancels above £5k. LangGraph's subgraph triggers and cron-based invocation make this composable without changing the core agent structure.

### 4. Competitor rate intelligence via MCP

The `get_as_of_otb` HITL gate exists precisely because some operations need external data before the agent can reason. Competitor rate shopping (OTA rate scrape, channel parity check) is the natural MCP server to bolt in. An MCP tool returning `{competitor_bar, parity_gap, channel}` gives the segment analysis skill real market context — not just "OTA is 50% of our mix" but "OTA is 50% of our mix and we're £12 below comp set."

### 5. Persistent long-term memory across stays and seasons

The current `InMemorySaver` checkpointer is session-scoped. For a GM who has been using the agent for 12 months, the memory layer should surface seasonal patterns: "Last July you had the same OTA concentration issue and tightened non-refundable rates two weeks out — that moved ADR £8." This requires a durable memory backend (Postgres or vector store) with a retrieval skill that surfaces relevant historical context before the agent answers.

### 6. PMS integration and live data sync

The ETL today is a daily batch scrape. Production requires a PMS webhook or polling integration so OTB is updated within minutes of a booking or cancellation. The tool layer already isolates the DB contract — swapping the ETL backend from scrape to live API is a data pipeline change, not an agent change. This is the architecture's key correctness bet: the tools own the grain, the agent never touches raw records.

### 7. Deeper subagent specialisation

The current segment-analyst subagent handles mix questions. The pattern scales to a `yield-optimizer` subagent that owns all rate and inventory decisions, a `group-coordinator` subagent that handles contract and block negotiation context, and an `events-impact` subagent that pulls local demand signals (concerts, conferences) and maps them to pickup patterns. Each subagent gets its own skill pack and tool surface — the orchestrator decides who to call.

---

## Submission

See [SUBMISSION.md](SUBMISSION.md) for the live URL, health endpoint, and full phase checklist.
