# Application Flow — Hotel Revenue Manager Agent

## Overview

This system is a hotel revenue management AI assistant for the otel.ai hackathon challenge. It has two independent subsystems:

1. **ETL Pipeline** — scrapes reservation data from a web source, transforms it, and loads it into PostgreSQL.
2. **Agent API** — a LangGraph AI agent exposed via FastAPI that answers revenue questions by querying the database.

---

## System Architecture

```
┌──────────────────────────────────────────┐
│              Data Source                 │
│  otel-hackathon-data-site.vercel.app     │
└───────────────────┬──────────────────────┘
                    │ Playwright scrape
                    ▼
┌──────────────────────────────────────────┐
│            ETL Pipeline                  │
│  scraper.py → transform.py → load.py    │
└───────────────────┬──────────────────────┘
                    │ psycopg2 upsert
                    ▼
┌──────────────────────────────────────────┐
│         PostgreSQL (Docker)              │
│  reservations_hackathon + lookup tables  │
└───────────────────┬──────────────────────┘
                    │ SQL queries
                    ▼
┌──────────────────────────────────────────┐
│         Revenue Tools (5 tools)          │
│  tools/revenue_tools.py                  │
└───────────────────┬──────────────────────┘
                    │ LangChain @tool
                    ▼
┌──────────────────────────────────────────┐
│       LangGraph Agent                    │
│  agent/revenue_agent.py                  │
└───────────────────┬──────────────────────┘
                    │ FastAPI endpoints
                    ▼
┌──────────────────────────────────────────┐
│         REST / WebSocket API             │
│  api/main.py (port 8000)                 │
└──────────────────────────────────────────┘
```

---

## Part 1: ETL Pipeline

**Entry point:** `python -m etl.run_etl` → `etl/run_etl.py::main()`

### Phase 1 — Extract (scraper.py)

`run_etl.py::main()` calls `etl/scraper.py::run_scraper()`

```
run_scraper()
├── Launch headless Chromium via Playwright
├── scrape_reference_data(page)
│   ├── Navigate to /reference
│   └── scrape_reference_tab() × 5 tabs:
│       ├── "Room types"          → room_types[]
│       ├── "Markets"             → market_codes[]
│       ├── "Channels"            → channel_codes[]
│       ├── "Rate plans"          → rate_plans[]
│       └── "Macro history"       → macro_group_history[]
├── scrape_verify_page(page)
│   └── Navigate to /verify → parse expected row counts
├── scrape_all_reservation_ids(page)
│   ├── Navigate to /reservations
│   ├── get_reservation_ids_from_page() — extract R* href links
│   └── Loop: click "Next" button until disabled → collect all IDs
└── scrape_reservation_detail(page, reservation_id) × N
    ├── Navigate to /reservations/{id}
    ├── Parse key-value fields from page body text
    │   └── known_fields = {arrival_date, departure_date, nights, ...}
    └── Extract stay_rows table (stay_date, financial_status, revenue cols)
Returns: {scraped_at, reference, verify, reservations[], scrape_manifest}
```

**Output:** `etl/raw_data.json`, `etl/SCRAPE_MANIFEST.json`

### Phase 2 — Transform (transform.py)

`run_etl.py::main()` calls `etl/transform.py::transform_raw_data(raw_data)`

```
transform_raw_data(raw_data)
├── transform_reference_data(reference)
│   ├── Map room_types[] → {space_type, room_class, display_name, number_of_rooms}
│   ├── Map rate_plans[] → {rate_plan_code, plan_family, is_commissionable}
│   ├── Map market_codes[] → {market_code, market_name, macro_group}
│   ├── Map channel_codes[] → {channel_code, channel_name, channel_group}
│   └── Map macro_group_history[] → {market_code, valid_from, valid_to, macro_group}
└── transform_reservations(reservations[], known_FKs...)
    └── For each reservation:
        ├── parse_date() / parse_datetime() / parse_bool() / parse_decimal()
        ├── Normalize reservation_status → "Reserved" | "Cancelled"
        ├── Validate FKs (space_type, market_code, channel_code)
        ├── infer_plan_family(rate_plan_code) for unknown plans
        ├── If stay_rows present (from scraper):
        │   └── Map each row → one DB record (grain: reservation × stay_date)
        └── Else (fallback): expand from arrival/departure date range

Returns: {room_types, rate_plans, market_codes, channel_codes,
          market_macro_group_history, reservation_rows[]}
```

**Grain:** One row per `(reservation_id, stay_date)` — a multi-night booking produces N rows.

### Phase 3 — Load (load.py)

`run_etl.py::main()` calls `etl/load.py::run_load(transformed_data, scrape_manifest)`

```
run_load(transformed_data, scrape_manifest)
├── get_connection() → psycopg2 to PostgreSQL
├── apply_schema(conn) → execute schema.sql (CREATE TABLE IF NOT EXISTS)
├── apply_views(conn) → execute sql/views.sql (semantic views)
├── ensure_default_lookup_data(conn) → insert defaults if tables empty
├── load_room_types(conn, ...)     → INSERT ... ON CONFLICT DO UPDATE
├── load_rate_plans(conn, ...)     → INSERT ... ON CONFLICT DO UPDATE
├── load_market_codes(conn, ...)   → INSERT ... ON CONFLICT DO UPDATE
├── load_channel_codes(conn, ...)  → INSERT ... ON CONFLICT DO UPDATE
├── load_macro_group_history(conn, ...)
├── load_reservations(conn, rows)
│   └── Batched upsert (500 rows/batch) into reservations_hackathon
│       ON CONFLICT (reservation_id, stay_date) DO UPDATE
├── compute_row_hash(rows) → SHA-256 of sorted reservation_id|stay_date|status
└── insert_load_manifest(conn, ...) → record in load_manifest table

Returns: {status, rows_loaded, dataset_revision, row_hash}
```

---

## Part 2: Agent API

**Entry point:** `python -m api.main` or `uvicorn api.main:app --port 8000`

### Startup

```
api/main.py
├── FastAPI app created with CORS middleware (allow all origins)
├── HTTPBasic security (APP_USERNAME / APP_PASSWORD from .env)
└── Endpoints registered (see below)
```

LangGraph agents are **lazy-initialized** on first request via module-level singletons:
- `get_main_agent()` → calls `create_agent()` once and caches result
- `get_segment_subagent()` → calls `create_segment_subagent()` once and caches result

### LLM Selection

`agent/revenue_agent.py::get_llm()` — called once at agent creation time:

```
get_llm()
├── Check LLM_PROVIDER env var (default: "auto")
├── "groq" or (auto + GROQ_API_KEY set)   → ChatGroq (llama-3.3-70b-versatile)
├── "openai" or (auto + OPENAI_API_KEY)   → ChatOpenAI (gpt-4o-mini)
└── else (ANTHROPIC_API_KEY)              → ChatAnthropic (claude-opus-4-6)
```

### Main Agent Graph (LangGraph)

`create_agent()` builds a `StateGraph[AgentState]`:

```
AgentState = {
    messages: list[BaseMessage],       # full conversation history
    pending_as_of_approval: bool,      # HITL flag
    pending_as_of_args: dict | None    # args waiting for approval
}

Nodes:
  "agent"           → call_model()
  "tools"           → execute_tools()
  "handle_approval" → handle_approval()

Edges:
  START → "agent"
  "agent" --[has tool_calls?]--> "tools"
  "agent" --[no tool_calls]--→ END
  "tools" --[pending approval?]--> END   (wait for user)
  "tools" --[no pending]------→ "agent"  (continue loop)
  "handle_approval" → "agent"
```

### Request Flow — `/chat/stream` (most detailed)

This is the primary endpoint used by the UI.

```
POST /chat/stream  {message, history[]}
│
├── verify_credentials() — HTTP Basic Auth check
│
└── chat_stream_endpoint()
    └── StreamingResponse(generate())
        └── chat_stream(message, history)  [agent/revenue_agent.py]
            │
            ├── _build_messages(message, history)
            │   └── Convert history dicts → HumanMessage / AIMessage objects
            │       Append new HumanMessage at end
            │
            ├── get_triggered_skill_names(message)
            │   └── For each SKILL_TRIGGERS entry, check if keyword in query
            │       Yield {"type": "skill", "name": "SKILL_OTB_HEALTH"} etc.
            │
            ├── Check _SUBAGENT_KEYWORDS in message
            │   If "segment mix" / "ota dependency" / etc. →
            │   └── Segment Subagent path (see below)
            │
            └── Main Agent path:
                ├── Build AgentState with messages
                └── agent.astream(state)  [LangGraph]
                    │
                    ├── [NODE: agent] call_model(state)
                    │   ├── Find last HumanMessage in state for skill lookup
                    │   ├── load_relevant_skills(recent_query)
                    │   │   └── load_skill(name) → read skills/{NAME}.md
                    │   ├── Build SystemMessage with skills injected into prompt
                    │   └── llm_with_tools.invoke([system_msg] + messages)
                    │       └── LLM decides: answer directly OR call tool(s)
                    │           Yield {"type": "tool_call", "name": ..., "args": ...}
                    │
                    ├── [EDGE] should_continue()
                    │   ├── AI message has tool_calls? → route to "tools"
                    │   └── No tool_calls? → END, yield {"type": "text", ...}
                    │
                    ├── [NODE: tools] execute_tools(state)
                    │   └── For each tool_call in last AI message:
                    │       ├── tool_name == "get_as_of_otb"?
                    │       │   ├── Set pending_as_of_approval = True
                    │       │   └── Emit approval request ToolMessage (HITL gate)
                    │       └── else:
                    │           ├── TOOL_MAP[tool_name].invoke(args)
                    │           │   └── Calls revenue_tools.py function
                    │           │       └── db.query() / db.query_one()
                    │           │           └── psycopg2 → PostgreSQL
                    │           └── Append ToolMessage(result_str)
                    │           Yield {"type": "tool_result", "name": ..., "preview": ...}
                    │
                    ├── [EDGE] should_continue_after_tools()
                    │   ├── pending_as_of_approval? → END (wait for user)
                    │   └── else → back to "agent" (loop continues)
                    │
                    └── Loop until no more tool calls → final AI text response
                        Yield {"type": "text", "content": final_response}
                        Yield {"type": "done"}
```

**SSE event stream to client:**
```
data: {"type": "skill",       "name": "SKILL_OTB_HEALTH"}
data: {"type": "tool_call",   "name": "get_otb_summary", "args": {"stay_month": "2025-07"}}
data: {"type": "tool_result", "name": "get_otb_summary", "preview": "room_nights: 420, ..."}
data: {"type": "text",        "content": "We have 420 room nights on the books for July..."}
data: {"type": "done"}
```

### Human-in-the-Loop (HITL) for `get_as_of_otb`

```
User asks: "What was our OTB for July as of June 1st?"
│
├── [agent node] LLM emits tool_call for get_as_of_otb
├── [tools node] execute_tools() detects "get_as_of_otb"
│   ├── Does NOT execute the tool
│   ├── Sets pending_as_of_approval = True, pending_as_of_args = {stay_month, as_of_utc}
│   └── Returns ToolMessage with approval request text
│
├── [edge] should_continue_after_tools() → pending=True → END
│   Client sees approval prompt, graph pauses
│
└── User replies "yes" (next API call with history)
    ├── [edge] route_human_message() → "handle_approval" (because pending=True)
    ├── [node: handle_approval] handle_approval(state)
    │   ├── Check last HumanMessage for "yes"/"approve"/"ok"/etc.
    │   ├── get_as_of_otb.invoke(pending_args) → direct tool execution
    │   └── Build AIMessage with formatted result
    └── [edge] handle_approval → "agent" → generate final narrative response
```

### Segment Subagent Path

Triggered when query contains: "segment mix", "ota dependency", "segment breakdown", "market mix", "block vs transient"

```
create_segment_subagent() → smaller StateGraph:
  Nodes: "agent", "tools"
  Tools: [get_segment_mix, get_block_vs_transient_mix] only
  System prompt: focused segment analyst persona
  Loop: agent → tools → agent → ... → END

Flow:
  chat_stream() detects keyword
  └── subagent.ainvoke({messages})
      └── Returns final AIMessage content
      Yield {"type": "text", "content": ...}
      Yield {"type": "done"}
```

### Other API Endpoints

| Endpoint | Auth | Handler | Description |
|---|---|---|---|
| `GET /health` | No | `health_check()` | DB fingerprint + load manifest |
| `POST /chat` | Basic | `chat_endpoint()` | Non-streaming chat via `chat()` |
| `POST /chat/stream` | Basic | `chat_stream_endpoint()` | SSE streaming via `chat_stream()` |
| `WS /ws/chat` | No | `websocket_chat()` | WebSocket chat (word-by-word simulated stream) |
| `GET /api/otb/{stay_month}` | Basic | `get_otb()` | Direct OTB data endpoint |
| `GET /api/segments/{stay_month}` | Basic | `get_segments()` | Direct segment data endpoint |

---

## Part 3: Revenue Tools (tools/revenue_tools.py)

All tools are decorated with `@tool` (LangChain) and call `db.query()` / `db.query_one()` which use a psycopg2 connection to PostgreSQL.

| Tool | SQL Target | What It Returns |
|---|---|---|
| `get_otb_summary(stay_month)` | `vw_stay_night_base` | Aggregate: room_nights, room_revenue, total_revenue, ADR |
| `get_segment_mix(stay_month)` | `vw_segment_stay_night` | Rows per market_code with share of room nights/revenue |
| `get_pickup_delta(days, from_date)` | `reservations_hackathon` | New bookings in last N days for future stays; by-segment breakdown |
| `get_as_of_otb(stay_month, as_of_utc)` | `reservations_hackathon` | Point-in-time OTB (HITL gated) |
| `get_block_vs_transient_mix(stay_month)` | `vw_stay_night_base` | Block vs transient split; top 3 companies by revenue |

`tools/db.py::get_db()` — context manager that opens/closes a psycopg2 connection per call. Uses `RealDictCursor` so rows are returned as `dict`.

---

## Part 4: Skills System (skills/)

Skills are plain Markdown files loaded at query-time to inject domain knowledge into the system prompt. They are NOT pre-loaded — they are loaded per-query based on keyword matching.

```
Skill trigger flow:
  User message → get_triggered_skill_names(message)
  └── SKILL_TRIGGERS dict: keyword patterns per skill name
      Matches → load_skill(name) → read skills/{NAME}.md
      All matched skills concatenated → injected into system prompt

SKILL_TRIGGERS keywords:
  SKILL_OTB_HEALTH        ← "otb", "revenue", "pace", "looking"
  SKILL_SEGMENT_ANALYSIS  ← "segment", "ota", "channel", "retail"
  SKILL_PICKUP_ANALYSIS   ← "pickup", "last week", "last 7"
  SKILL_GROUP_ANALYSIS    ← "group", "block", "transient"
  SKILL_CANCELLATION_RISK ← "cancel", "risk", "as of"
  SKILL_ROOM_TYPE_MIX     ← "room type", "suite", "deluxe"
  CHALLENGE_SKILL         ← "briefing", "comprehensive", "overview"
```

---

## Part 5: Database Schema

**PostgreSQL 16 (Docker, port 5433 external / 5432 internal)**

```
Lookup tables (static reference):
  room_type_lookup        (space_type PK)
  rate_plan_lookup        (rate_plan_code PK)
  market_code_lookup      (market_code PK)
  channel_code_lookup     (channel_code PK)
  market_macro_group_history (market_code + valid_from PK)

Fact table (one row per reservation × stay_date):
  reservations_hackathon
    PK: reservation_stay_id (identity)
    UNIQUE: (reservation_id, stay_date)
    FKs: space_type → room_type_lookup
         market_code → market_code_lookup
         channel_code → channel_code_lookup
         rate_plan_code → rate_plan_lookup
    Indexes: stay_date, property_date, create_datetime,
             market_code, channel_code, reservation_status, financial_status

Audit:
  load_manifest           (load_id PK, row_hash, dataset_revision)
```

**Semantic views** (applied by `load.py::apply_views()` from `sql/views.sql`):
- `vw_stay_night_base` — Posted, non-cancelled rows only
- `vw_segment_stay_night` — Adds effective_macro_group via time-effective join to market_macro_group_history

---

## Startup Sequence (Full System)

```
1. docker compose up -d          → PostgreSQL container starts (port 5433)
2. python -m etl.run_etl         → ETL pipeline: scrape → transform → load
3. uvicorn api.main:app --port 8000  → FastAPI server starts
4. Client POST /chat/stream       → First request initializes LangGraph agent
```

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| Grain: (reservation_id × stay_date) | Allows per-night revenue analysis and point-in-time OTB rebuild |
| LangGraph for agent | Built-in state management for multi-turn HITL flows |
| Skills as Markdown files | Progressive disclosure — only relevant domain context loaded per query |
| Segment subagent | Keeps segment analysis focused; avoids polluting main agent with specialist tools |
| HITL gate on `get_as_of_otb` | Expensive DB scan; requires explicit user approval before running |
| Idempotent upsert in load | Re-running ETL is safe; ON CONFLICT DO UPDATE prevents duplicates |
| `vw_stay_night_base` view | Agents never write raw filter SQL; single source of truth for "active OTB" |
