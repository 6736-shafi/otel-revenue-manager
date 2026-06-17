"""
Streamlit UI for the Hotel Revenue Manager Agent.
Supports two modes:
  - Direct Query Mode: calls tools directly (no LLM API key needed)
  - Chat Mode: full AI agent (requires OPENAI_API_KEY or ANTHROPIC_API_KEY with credits)
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, date
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

st.set_page_config(
    page_title="Hotel Revenue Manager",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px;
}
.metric-card {
    background: #f8f9fa; border: 1px solid #dee2e6;
    border-radius: 8px; padding: 15px; margin: 5px 0;
}
.risk-high { color: #dc3545; font-weight: bold; }
.risk-watch { color: #fd7e14; font-weight: bold; }
.risk-ok { color: #28a745; font-weight: bold; }
.login-box {
    max-width: 380px; margin: 80px auto; padding: 40px;
    border: 1px solid #dee2e6; border-radius: 12px;
    background: #ffffff; box-shadow: 0 4px 20px rgba(0,0,0,0.08);
}
</style>
""", unsafe_allow_html=True)

# ── Login gate ────────────────────────────────────────────────────────────────
APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "revenue2025")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("""
    <div class="login-box">
        <h2 style="text-align:center; margin-bottom:8px;">🏨 Revenue Manager</h2>
        <p style="text-align:center; color:#666; margin-bottom:24px;">Sign in to continue</p>
    </div>
    """, unsafe_allow_html=True)

    col = st.columns([1, 2, 1])[1]
    with col:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Sign in", use_container_width=True, type="primary"):
            import secrets as _sec
            if _sec.compare_digest(username, APP_USERNAME) and _sec.compare_digest(password, APP_PASSWORD):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()

# ── Authenticated ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>🏨 Hotel Revenue Manager</h1>
    <p>AI-powered Revenue Intelligence for Hotel GMs</p>
</div>
""", unsafe_allow_html=True)


def check_db():
    try:
        from tools.db import query_one
        r = query_one("SELECT COUNT(*) AS cnt FROM public.reservations_hackathon")
        return True, int((r or {}).get("cnt", 0))
    except Exception as e:
        return False, str(e)


def check_llm():
    """Check if LLM API key is available and working."""
    provider = os.environ.get("LLM_PROVIDER", "auto").lower()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if provider == "deepseek" and deepseek_key:
        return True, "DeepSeek"
    if provider == "github" and github_token:
        return True, "GitHub Models (GPT-4o)"
    if provider == "groq" and groq_key:
        return True, "Groq"
    if provider == "openai" and openai_key:
        return True, "OpenAI"
    if provider == "anthropic" and anthropic_key:
        return True, "Anthropic (check credits)"
    if deepseek_key:
        return True, "DeepSeek"
    if groq_key:
        return True, "Groq"
    if openai_key:
        return True, "OpenAI"
    if anthropic_key:
        return True, "Anthropic (check credits)"
    return False, "No API key"


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def fmt_gbp(v):
    return f"£{float(v or 0):,.0f}"

def fmt_pct(v):
    return f"{float(v or 0):.1f}%"

def risk_badge(val, high_thresh, watch_thresh, higher_is_bad=True):
    v = float(val or 0)
    if higher_is_bad:
        if v >= high_thresh:
            return f'<span class="risk-high">🔴 {v:.1f}%</span>'
        elif v >= watch_thresh:
            return f'<span class="risk-watch">🟡 {v:.1f}%</span>'
        return f'<span class="risk-ok">🟢 {v:.1f}%</span>'
    else:
        if v >= high_thresh:
            return f'<span class="risk-ok">🟢 {v:.1f}%</span>'
        elif v >= watch_thresh:
            return f'<span class="risk-watch">🟡 {v:.1f}%</span>'
        return f'<span class="risk-high">🔴 {v:.1f}%</span>'


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Status")

    db_ok, db_info = check_db()
    if db_ok:
        st.success(f"✅ Database: {db_info:,} rows")
    else:
        st.error(f"❌ DB: {db_info}")
        st.info("Run `docker compose up -d` then `make etl`")

    llm_ok, llm_name = check_llm()
    if llm_ok and "check credits" not in llm_name.lower():
        st.success(f"✅ LLM: {llm_name}")
    else:
        st.warning(f"⚠️ LLM: {llm_name}")
        st.info("Add `GROQ_API_KEY=...` to `.env` for Chat Mode")

    st.markdown("---")
    mode = st.radio("**Mode**", ["📊 Direct Query", "💬 Chat with AI"],
                    help="Direct Query works without an API key")

    st.markdown("---")
    if st.button("🗑️ Clear", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    if st.button("🔓 Sign out", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()


# ── DIRECT QUERY MODE ─────────────────────────────────────────────────────────
if mode == "📊 Direct Query":
    st.markdown("### 📊 Direct Revenue Dashboard")
    st.caption("No API key required — queries the database directly.")

    if not db_ok:
        st.error("Database not connected. Start it with `docker compose up -d` and run ETL.")
        st.stop()

    from tools.revenue_tools import (
        get_otb_summary, get_segment_mix,
        get_pickup_delta, get_block_vs_transient_mix,
    )

    # Month selector
    col1, col2 = st.columns([2, 3])
    with col1:
        today = date.today()
        default_month = today.strftime("%Y-%m")
        stay_month = st.text_input("Stay Month (YYYY-MM)", value=default_month)

    with col2:
        future_from = st.text_input("Pickup From (YYYY-MM-DD)", value=today.strftime("%Y-%m-%d"))
        pickup_days = st.selectbox("Pickup Window (days)", [7, 14, 30], index=0)

    # Auto-load on page open — data refreshes whenever inputs change
    try:
        otb = get_otb_summary.invoke({"stay_month": stay_month})
        segments = get_segment_mix.invoke({"stay_month": stay_month})
        pickup = get_pickup_delta.invoke({"booking_window_days": pickup_days, "future_stay_from": future_from})
        block = get_block_vs_transient_mix.invoke({"stay_month": stay_month})

        # ── OTB Summary ──
        st.markdown(f"#### 📈 OTB Summary — {stay_month}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Reservations", f"{otb.get('reservation_count', 0):,}")
        c2.metric("Room Nights", f"{otb.get('room_nights', 0):,}")
        c3.metric("Room Revenue", fmt_gbp(otb.get('room_revenue', 0)))
        c4.metric("ADR", fmt_gbp(otb.get('adr', 0)))
        st.metric("Total Revenue (incl. packages)", fmt_gbp(otb.get('total_revenue', 0)))

        # ── Pickup ──
        st.markdown(f"#### ⚡ Pickup — last {pickup_days} days for stays from {future_from}")
        pc1, pc2, pc3 = st.columns(3)
        pc1.metric("New Reservations", f"{pickup.get('new_reservations', 0):,}")
        pc2.metric("New Room Nights", f"{pickup.get('new_room_nights', 0):,}")
        pc3.metric("New Revenue", fmt_gbp(pickup.get('new_total_revenue', 0)))

        by_seg = pickup.get("by_segment", [])
        if by_seg:
            st.markdown("**By Segment:**")
            for s in by_seg[:5]:
                st.markdown(f"- **{s['market_name']}** ({s['market_code']}): "
                            f"{s['new_room_nights']} RN · {fmt_gbp(s['new_total_revenue'])}")

        # ── Segment Mix ──
        st.markdown(f"#### 🎯 Segment Mix — {stay_month}")
        if segments and not segments[0].get("error"):
            seg_rows = []
            for s in segments:
                share_rn = s.get("share_of_room_nights", 0)
                flag = ""
                if s.get("market_code") == "OTA":
                    if share_rn > 50:
                        flag = "🔴 HIGH RISK"
                    elif share_rn > 30:
                        flag = "🟡 WATCH"
                    else:
                        flag = "🟢"
                seg_rows.append({
                    "Segment": f"{s.get('market_name')} ({s.get('market_code')})",
                    "Macro Group": s.get("macro_group", ""),
                    "Room Nights": s.get("room_nights", 0),
                    "Revenue": fmt_gbp(s.get("total_revenue", 0)),
                    "RN Share": fmt_pct(share_rn),
                    "Rev Share": fmt_pct(s.get("share_of_revenue", 0)),
                    "Flag": flag,
                })
            import pandas as pd
            st.dataframe(pd.DataFrame(seg_rows), width='stretch', hide_index=True)

        # ── Block vs Transient ──
        st.markdown(f"#### 🏢 Group vs Transient — {stay_month}")
        if "error" not in block:
            b1, b2 = st.columns(2)
            block_share = block.get("block_share_of_room_nights", 0)
            block_flag = "🔴 Displacement Risk" if block_share > 40 else ("🟡 Watch" if block_share > 30 else "🟢 Healthy")
            with b1:
                st.markdown("**Group (Block)**")
                st.metric("Room Nights", f"{block.get('block_room_nights', 0):,}")
                st.metric("Revenue", fmt_gbp(block.get("block_total_revenue", 0)))
                st.markdown(f"Share: **{block_share:.1f}%** {block_flag}")
            with b2:
                st.markdown("**Transient**")
                st.metric("Room Nights", f"{block.get('transient_room_nights', 0):,}")
                st.metric("Revenue", fmt_gbp(block.get("transient_total_revenue", 0)))
            top_cos = block.get("top_companies", [])
            if top_cos:
                st.markdown("**Top Group Companies:**")
                for co in top_cos:
                    st.markdown(f"- {co['company_name']}: {co['room_nights']} RN · {fmt_gbp(co['total_revenue'])}")
                top3_share = block.get("top3_company_revenue_share", 0)
                conc_flag = "🔴 HIGH RISK" if top3_share > 50 else ("🟡 Watch" if top3_share > 30 else "🟢")
                st.markdown(f"Top-3 concentration: **{top3_share:.1f}%** {conc_flag}")

        st.success("✅ Analysis complete")
    except Exception as e:
        st.error(f"Error: {e}")

    # Quick month buttons
    st.markdown("---")
    st.caption("Quick select:")
    months = []
    today = date.today()
    for i in range(6):
        m = today.month + i
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        months.append(f"{y:04d}-{m:02d}")

    cols = st.columns(6)
    for i, (col, m) in enumerate(zip(cols, months)):
        if col.button(m, key=f"qm_{i}"):
            st.session_state["quick_month"] = m
            st.rerun()


# ── CHAT MODE ─────────────────────────────────────────────────────────────────
else:
    if not llm_ok:
        st.warning("""
**Chat Mode requires an API key.**

Add one of these to your `.env` file and restart:

```
GROQ_API_KEY=gsk_...your-groq-key...
LLM_PROVIDER=groq
```

Get a free key at: https://console.groq.com

**Alternatively, use 📊 Direct Query mode** (no API key needed) from the sidebar.
""")
        st.stop()

    if not db_ok:
        st.error("Database not connected.")
        st.stop()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Sample questions
    with st.sidebar:
        st.markdown("### 💡 Try asking:")
        samples = [
            "What revenue is on the books?",
            "Which segments are driving next month?",
            "How much group business do we have?",
            "What changed in the last 7 days?",
            "Are we too dependent on OTA?",
            "Give me the morning briefing",
        ]
        for q in samples:
            if st.button(q, key=f"q_{q[:15]}", width='stretch'):
                st.session_state.pending = q
                st.rerun()

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🏨" if msg["role"] == "assistant" else None):
            st.markdown(msg["content"])

    # Handle input
    pending = st.session_state.pop("pending", None)
    user_input = pending or st.chat_input("Ask your Revenue Manager...")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar="🏨"):
            import threading
            import queue as _queue

            # Capture history in main thread BEFORE spawning background thread
            # (st.session_state is not accessible from background threads)
            history_msgs = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages[:-1]
            ]
            event_q = _queue.Queue()

            def _run_stream(captured_history):
                from agent.revenue_agent import chat_stream
                import asyncio
                async def _go():
                    async for ev in chat_stream(user_input, captured_history):
                        event_q.put(ev)
                try:
                    asyncio.run(_go())
                except Exception as exc:
                    event_q.put({"type": "error", "content": str(exc)})
                    event_q.put({"type": "done"})

            thread = threading.Thread(target=_run_stream, args=(history_msgs,), daemon=True)
            thread.start()

            response_text = ""
            with st.status("🔍 Analyzing revenue data...", expanded=True) as status:
                while True:
                    try:
                        ev = event_q.get(timeout=90)
                    except _queue.Empty:
                        if not thread.is_alive():
                            break
                        continue

                    if ev["type"] == "skill":
                        st.write(f"📖 Loaded skill `{ev['name']}`")
                    elif ev["type"] == "tool_call":
                        args_str = ", ".join(
                            f"{k}=`{v}`" for k, v in ev.get("args", {}).items()
                        )
                        st.write(f"🔧 Calling `{ev['name']}({args_str})`")
                    elif ev["type"] == "tool_result":
                        st.write(f"✅ `{ev['name']}` → {ev.get('preview', '')[:120]}")
                    elif ev["type"] == "text":
                        response_text = ev["content"]
                    elif ev["type"] == "error":
                        err = ev["content"]
                        if "credit balance" in err.lower() and "billing" in err.lower() and "rate_limit" not in err.lower():
                            response_text = (
                                "⚠️ **API has no credits.**\n\n"
                                "Add a valid API key to `.env` and restart, "
                                "or switch to **📊 Direct Query** mode."
                            )
                        elif "rate_limit" in err.lower() or "tokens per minute" in err.lower() or "413" in err:
                            response_text = (
                                "⚠️ **Rate limit hit** (request too large for free tier).\n\n"
                                f"Details: {err[:300]}"
                            )
                        else:
                            response_text = f"⚠️ Error: {err}"
                    elif ev["type"] == "approval_required":
                        response_text = ev["content"]
                        st.session_state["pending_approval"] = True
                    elif ev["type"] == "done":
                        break

                thread.join(timeout=5)
                if response_text:
                    status.update(label="✅ Analysis complete", state="complete", expanded=False)
                else:
                    status.update(label="⚠️ No response", state="error", expanded=False)

            if response_text:
                st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text or "⚠️ No response received."})

    if not st.session_state.messages:
        st.markdown("""
<div style="text-align:center; padding:40px; color:#666;">
    <h3>👋 Welcome to your Revenue Manager</h3>
    <p>Ask me about revenue, segments, pickup pace, or group business.</p>
    <p><em>Or switch to <b>📊 Direct Query</b> mode (no API key needed)</em></p>
</div>
""", unsafe_allow_html=True)
