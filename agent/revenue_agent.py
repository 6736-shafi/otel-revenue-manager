"""
Revenue Manager Agent — built on LangChain Deep Agents (deepagents).

Framework building blocks used:
  - create_deep_agent()       : harness entry point
  - skills=["skills/"]      : on-demand SKILL.md progressive disclosure
  - memory=["memory/AGENTS.md"]: persistent revenue-manager context
  - subagents=[SEGMENT_SUBAGENT]: segment/mix work routed to specialist
  - interrupt_on={"get_as_of_otb": True}: HITL gate on expensive tool
  - FilesystemBackend         : virtual filesystem + skill loading from disk
  - InMemorySaver checkpointer: multi-turn conversation persistence by thread_id
  - TodoListMiddleware         : built-in planning (via create_deep_agent base stack)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage, AIMessage
from deepagents.graph import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.subagents import SubAgent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.revenue_tools import (
    get_otb_summary,
    get_segment_mix,
    get_pickup_delta,
    get_as_of_otb,
    get_block_vs_transient_mix,
    ALL_TOOLS,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_DIR = "skills/"          # relative to PROJECT_ROOT (FilesystemBackend root)
MEMORY_FILE = "memory/AGENTS.md"  # relative to PROJECT_ROOT

TOOL_MAP = {t.name: t for t in ALL_TOOLS}


def get_llm(model_name: str | None = None, temperature: float = 0.1):
    """Get LLM. Priority: LLM_PROVIDER env var, then auto-detect from available keys."""
    provider = os.environ.get("LLM_PROVIDER", "auto").lower()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        m = model_name or os.environ.get("OLLAMA_MODEL", "llama3.2")
        return ChatOllama(model=m, base_url=ollama_base, temperature=temperature)
    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        m = model_name or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        return ChatOpenAI(
            model=m,
            temperature=temperature,
            api_key=deepseek_key,
            base_url="https://api.deepseek.com/v1",
        )
    elif provider == "groq" or (provider == "auto" and groq_key):
        from langchain_groq import ChatGroq
        m = model_name or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        return ChatGroq(model=m, temperature=temperature, api_key=groq_key)
    elif provider == "openai" or (provider == "auto" and openai_key):
        from langchain_openai import ChatOpenAI
        m = model_name or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=m, temperature=temperature, api_key=openai_key)
    else:
        from langchain_anthropic import ChatAnthropic
        m = model_name or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6")
        return ChatAnthropic(model=m, temperature=temperature, api_key=anthropic_key)


def _build_system_prompt() -> str:
    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("Europe/London"))
    today = now.strftime("%Y-%m-%d")
    current_month = now.strftime("%Y-%m")
    next_month_dt = (now.replace(day=1) + __import__("datetime").timedelta(days=32)).replace(day=1)
    next_month = next_month_dt.strftime("%Y-%m")
    return f"""You are an expert Hotel Revenue Manager AI assistant, working for the General Manager.

## Today's Date
Today is {today} (London time). Current stay month: {current_month}. Next month: {next_month}.
Never ask the user what the date is — use these values directly when calling tools.

## Your Role
1. Answer revenue management questions using the available tools
2. Translate raw data into commercial insights and recommended actions
3. Speak like a sharp revenue manager in a morning briefing — confident, data-driven, actionable
4. Apply judgment thresholds loaded from skills to flag risks and opportunities

## Tools Available
- `get_otb_summary(stay_month, exclude_cancelled)` — OTB metrics for a month
- `get_segment_mix(stay_month, macro_group)` — Segment/market breakdown
- `get_pickup_delta(booking_window_days, future_stay_from)` — Recent booking pace
- `get_as_of_otb(stay_month, as_of_utc)` — **REQUIRES HUMAN APPROVAL** — point-in-time snapshot
- `get_block_vs_transient_mix(stay_month)` — Group vs transient analysis

## Planning
For multi-part questions, use the todo list to decompose the work into steps before calling tools.

## CRITICAL: Human-in-the-Loop for get_as_of_otb
The framework will automatically request approval before running get_as_of_otb.
This is an expensive point-in-time database rebuild. Never attempt to bypass this gate.

## Answer Style
- Lead with the headline insight, not raw numbers
- Quantify key metrics (room nights, £ revenue, %)
- Flag 1–2 risks or opportunities
- End with a recommended action
- Use: "We have...", "At current pace...", "I'd recommend..."

## Date Conventions
- stay_date for monthly OTB and segment analysis (YYYY-MM format)
- create_datetime for pickup/pace questions
- Stay months: YYYY-MM (e.g. {current_month})
"""

SYSTEM_PROMPT = _build_system_prompt()

# Segment specialist subagent — routes segment/mix analysis to a focused agent
SEGMENT_SUBAGENT = SubAgent(
    name="segment-analyst",
    description=(
        "Specialized segment and block/transient mix analyst. "
        "Use for: segment mix breakdown by market code, OTA dependency check, "
        "block vs transient split, company concentration analysis. "
        "Triggers on: 'segment mix', 'OTA dependency', 'market mix', 'block vs transient'."
    ),
    system_prompt=(
        "You are a specialized Hotel Revenue Segment Analyst. "
        "Focus exclusively on market segment breakdown and block/transient analysis. "
        "Use get_segment_mix for segment share and get_block_vs_transient_mix for group analysis. "
        "Return: top 3 segments by room nights with shares, OTA dependency flag (>50% = high risk), "
        "block share assessment, company concentration, and one recommended action."
    ),
    tools=[get_segment_mix, get_block_vs_transient_mix],
)


def _make_backend() -> FilesystemBackend:
    return FilesystemBackend(root_dir=str(PROJECT_ROOT), virtual_mode=True)


_checkpointer: InMemorySaver | None = None
_main_agent = None


def get_checkpointer() -> InMemorySaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = InMemorySaver()
    return _checkpointer


def create_agent():
    """Create the Revenue Manager using deepagents create_deep_agent()."""
    llm = get_llm()

    return create_deep_agent(
        model=llm,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        skills=[SKILLS_DIR],
        memory=[MEMORY_FILE],
        subagents=[SEGMENT_SUBAGENT],
        backend=_make_backend(),
        checkpointer=get_checkpointer(),
        name="revenue-manager",
    )


def _use_lightweight() -> bool:
    """Use a lightweight ReAct agent when the provider can't handle deepagents overhead."""
    provider = os.environ.get("LLM_PROVIDER", "auto").lower()
    # github and deepseek use full deepagents stack with HITL
    return provider == "groq"


_lightweight_agent = None

def _create_lightweight_agent():
    """Simple LangGraph ReAct agent — ~600 tokens per request, works on Groq free tier."""
    from langgraph.prebuilt import create_react_agent
    llm = get_llm()
    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
        checkpointer=get_checkpointer(),
    )


def get_main_agent():
    global _main_agent, _lightweight_agent
    if _use_lightweight():
        if _lightweight_agent is None:
            _lightweight_agent = _create_lightweight_agent()
        return _lightweight_agent
    if _main_agent is None:
        _main_agent = create_agent()
    return _main_agent


def _thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _is_interrupted(thread_id: str) -> bool:
    """Return True if the agent graph is paused at an interrupt for this thread."""
    if _use_lightweight():
        return False  # lightweight agent has no HITL interrupts
    try:
        state = get_main_agent().get_state(_thread_config(thread_id))
        return bool(state.next)
    except Exception:
        return False


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") if isinstance(b, dict) else str(b)
            for b in content
        )
    return str(content) if content else ""


async def chat(message: str, history: list[dict] | None = None, thread_id: str = "default") -> str:
    """
    Process a chat message and return the agent response.

    thread_id scopes the conversation — the checkpointer persists state across calls.
    history is accepted for backward-compat but thread_id is the primary memory mechanism.
    """
    agent = get_main_agent()
    config = _thread_config(thread_id)
    msg_lower = message.lower().strip()

    if _is_interrupted(thread_id):
        if any(w in msg_lower for w in ["yes", "approve", "ok", "proceed", "go ahead", "run it", "sure"]):
            result = await agent.ainvoke(Command(resume=True), config=config)
        else:
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=message)]}, config=config
            )
    else:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]}, config=config
        )

    messages = result.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    return _extract_text(getattr(last, "content", ""))


async def chat_stream(message: str, history: list[dict] | None = None, thread_id: str = "default"):
    """
    Async generator yielding agent events for streaming UI visibility.

    Event types:
      {"type": "skill",            "name": "otb-health"}
      {"type": "tool_call",        "name": "get_otb_summary", "args": {...}}
      {"type": "tool_result",      "name": "get_otb_summary", "preview": "..."}
      {"type": "approval_required","content": "... approve? (yes/no)"}
      {"type": "text",             "content": "final response"}
      {"type": "done"}
      {"type": "error",            "content": "error message"}
    """
    try:
        agent = get_main_agent()
        config = _thread_config(thread_id)
        msg_lower = message.lower().strip()

        if _is_interrupted(thread_id):
            if any(w in msg_lower for w in ["yes", "approve", "ok", "proceed", "go ahead", "run it", "sure"]):
                input_data = Command(resume=True)
            else:
                input_data = {"messages": [HumanMessage(content=message)]}
        else:
            input_data = {"messages": [HumanMessage(content=message)]}

        final_content = ""

        async for event in agent.astream_events(input_data, config=config, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")
            data = event.get("data", {})

            if kind == "on_tool_start":
                args = data.get("input", {})
                # Detect skill file reads — surface as skill events
                if name in ("read_file", "ls") and isinstance(args, dict):
                    path = str(args.get("path", args.get("pattern", "")))
                    if "skills" in path and "SKILL.md" in path:
                        skill_name = Path(path).parent.name
                        yield {"type": "skill", "name": skill_name}
                    else:
                        yield {"type": "tool_call", "name": name, "args": args}
                elif name != "write_todos":  # suppress todo internals
                    yield {"type": "tool_call", "name": name, "args": args}

            elif kind == "on_tool_end":
                output = data.get("output", "")
                if name in ("read_file", "ls", "write_todos"):
                    continue  # don't surface filesystem internals as tool_result
                try:
                    parsed = json.loads(str(output)) if isinstance(output, str) else output
                    if isinstance(parsed, list):
                        preview = f"{len(parsed)} records"
                    elif isinstance(parsed, dict) and "error" not in parsed:
                        preview = ", ".join(f"{k}: {v}" for k, v in list(parsed.items())[:3])
                    else:
                        preview = str(parsed)[:150]
                except Exception:
                    preview = str(output)[:150]
                yield {"type": "tool_result", "name": name, "preview": preview}

            elif kind == "on_chat_model_stream":
                chunk = data.get("chunk", {})
                content = getattr(chunk, "content", "")
                if isinstance(content, str) and content:
                    final_content += content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            final_content += block.get("text", "")

        # Check if the graph is now waiting at a HITL interrupt
        state = agent.get_state(config)
        if state.next:
            yield {
                "type": "approval_required",
                "content": (
                    "⚠️ **Human Approval Required**\n\n"
                    "Running a point-in-time OTB rebuild requires an expensive database operation. "
                    "**Do you approve?** (Reply 'yes' to proceed, 'no' to cancel)"
                ),
            }
        elif final_content:
            yield {"type": "text", "content": final_content}

        yield {"type": "done"}

    except Exception as e:
        logger.error(f"chat_stream error: {e}", exc_info=True)
        yield {"type": "error", "content": str(e)}
        yield {"type": "done"}
