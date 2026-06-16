"""
FastAPI backend for the Revenue Manager Agent.
Provides REST endpoints and streaming WebSocket for the chat UI.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime, timezone
from functools import lru_cache
from typing import AsyncGenerator

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.db import query_one

logger = logging.getLogger(__name__)

APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "revenue2025")

app = FastAPI(
    title="Hotel Revenue Manager Agent",
    description="AI-powered Revenue Manager for hotel GMs",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Auth credentials."""
    correct_username = secrets.compare_digest(credentials.username, APP_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, APP_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    thread_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[dict] = []


@app.get("/health")
async def health_check():
    """Health check endpoint with database fingerprint."""
    try:
        manifest = query_one(
            """
            SELECT dataset_revision, row_hash, scraped_at::text
            FROM public.load_manifest
            ORDER BY load_id DESC
            LIMIT 1
            """
        )

        agg = query_one(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE reservation_status <> 'Cancelled'
                    AND financial_status = 'Posted'
                ) AS financial_status_posted_only_rows
            FROM public.reservations_hackathon
            """
        )

        # Compute db_fingerprint from pair hash
        import hashlib
        pairs_result = query_one(
            """
            SELECT STRING_AGG(
                reservation_id || '|' || stay_date::text || '|' || financial_status,
                chr(10)
                ORDER BY reservation_id, stay_date, financial_status
            ) AS pairs
            FROM public.reservations_hackathon
            """
        )
        pairs_str = (pairs_result or {}).get("pairs") or ""
        db_fingerprint = hashlib.sha256(pairs_str.encode()).hexdigest()

        return {
            "status": "healthy",
            "db_fingerprint": db_fingerprint,
            "dataset_revision": (manifest or {}).get("dataset_revision", "unknown"),
            "row_hash": (manifest or {}).get("row_hash", "unknown"),
            "financial_status_posted_only_rows": int((agg or {}).get("financial_status_posted_only_rows", 0)),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "db_fingerprint": "unavailable",
            "dataset_revision": "unavailable",
            "row_hash": "unavailable",
            "financial_status_posted_only_rows": 0,
        }


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    username: str = Depends(verify_credentials)
):
    """Chat with the Revenue Manager Agent."""
    from agent.revenue_agent import chat
    try:
        response = await chat(request.message, request.history, thread_id=request.thread_id)
        return ChatResponse(response=response)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    username: str = Depends(verify_credentials)
):
    """Streaming chat endpoint — emits SSE JSON events for tool calls, skills, and text."""
    from agent.revenue_agent import chat_stream
    import json as _json

    async def generate():
        try:
            async for event in chat_stream(request.message, request.history, thread_id=request.thread_id):
                yield f"data: {_json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            yield f"data: {_json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time streaming chat."""
    await websocket.accept()
    from agent.revenue_agent import chat

    import uuid
    ws_thread_id = str(uuid.uuid4())  # unique thread per WebSocket session

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")

            if not message:
                continue

            # Send typing indicator
            await websocket.send_json({"type": "typing", "content": "..."})

            try:
                response = await chat(message, thread_id=ws_thread_id)

                # Stream response (history persisted in checkpointer by ws_thread_id)
                words = response.split(" ")
                buffer = ""
                for i, word in enumerate(words):
                    buffer += word + (" " if i < len(words) - 1 else "")
                    if len(buffer) > 20 or i == len(words) - 1:
                        await websocket.send_json({"type": "chunk", "content": buffer})
                        buffer = ""
                        await asyncio.sleep(0.01)

                await websocket.send_json({"type": "done", "content": response})

            except Exception as e:
                await websocket.send_json({"type": "error", "content": str(e)})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")


@app.get("/api/otb/{stay_month}")
async def get_otb(stay_month: str, username: str = Depends(verify_credentials)):
    """Direct OTB summary endpoint."""
    from tools.revenue_tools import get_otb_summary
    result = get_otb_summary.invoke({"stay_month": stay_month})
    return result


@app.get("/api/segments/{stay_month}")
async def get_segments(stay_month: str, username: str = Depends(verify_credentials)):
    """Direct segment mix endpoint."""
    from tools.revenue_tools import get_segment_mix
    result = get_segment_mix.invoke({"stay_month": stay_month})
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
