"""
Chummah — FastAPI Backend
Main application: REST endpoints, SSE streaming, static file serving.
Run locally with: uvicorn main:app --reload --port 8000
"""

import sys
import os
import json
import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

# ── Ensure the backend directory is on sys.path (required for Vercel) ──
# Vercel runs main.py but doesn't automatically add its directory to sys.path
_backend_dir = Path(__file__).parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import init_db, create_session, update_session_title, add_message
from db import get_sessions, get_session, get_session_messages, get_recent_messages
from db import delete_session
from llm_client import stream_chat, check_health
from llm_client import parse_response_json
from prompt_builder import build_messages, generate_session_title

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("chummah")

# Frontend directory (served as static files — only available when running locally)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 Chummah starting up...")
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        # Non-fatal on Vercel cold start — DB will be lazy-initialized per request
        logger.warning(f"⚠️  DB init skipped at startup: {e}")

    yield

    logger.info("👋 Chummah shutting down")


app = FastAPI(
    title="Chummah",
    description="English Fluency Trainer — powered by Groq",
    version="1.0.0",
    lifespan=lifespan
)

# CORS — allow all origins (frontend is served separately on Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response Models ───────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    mode: str = "casual"            # 'interview' or 'casual'
    session_id: str | None = None   # None = create new session

class SessionCreate(BaseModel):
    mode: str = "casual"

# ─── Health Check ──────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        health = await check_health()
        return health
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(e)}
        )


# ─── Chat Endpoint (SSE Streaming) ─────────────────────────────────

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Main chat endpoint — streams the response via Server-Sent Events (SSE).

    SSE event types:
    - 'token': individual content token (for real-time display)
    - 'corrections': parsed corrections JSON (sent at the end)
    - 'meta': session info (session_id, message_id)
    - 'error': error message
    - 'done': signals completion
    """
    # Create or validate session
    session_id = req.session_id
    is_new_session = False

    if session_id is None:
        session_id = create_session(mode=req.mode)
        is_new_session = True
        logger.info(f"Created new session: {session_id}")
    else:
        session = get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    # Save user message to DB
    user_msg_id = add_message(
        session_id=session_id,
        role="user",
        original_text=req.message
    )

    # Update session title from first message
    if is_new_session:
        title = generate_session_title(req.message)
        update_session_title(session_id, title)

    # Build conversation context
    history = get_recent_messages(session_id, limit=6)
    messages = build_messages(req.mode, history[:-1], req.message)

    async def event_stream():
        """Generator that yields SSE events."""
        full_response = ""

        try:
            # Send session metadata first
            yield f"event: meta\ndata: {json.dumps({'session_id': session_id, 'user_msg_id': user_msg_id, 'is_new_session': is_new_session})}\n\n"

            # Stream tokens from Groq
            async for token in stream_chat(messages):
                full_response += token
                yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"

            # Parse the complete response for corrections
            parsed = parse_response_json(full_response)

            # Save bot message to DB
            corrections_data = {
                "grammar_fixes": parsed.get("grammar_fixes", []),
                "vocab_tips": parsed.get("vocab_tips", []),
                "alt_phrasings": parsed.get("alt_phrasings", [])
            }

            bot_msg_id = add_message(
                session_id=session_id,
                role="bot",
                display_text=parsed.get("reply", full_response),
                corrections=corrections_data
            )

            # Send parsed corrections
            yield f"event: corrections\ndata: {json.dumps(parsed)}\n\n"

            # Send completion signal with session title
            session_data = get_session(session_id)
            yield f"event: done\ndata: {json.dumps({'bot_msg_id': bot_msg_id, 'session_title': session_data['title'] if session_data else ''})}\n\n"

        except RuntimeError as e:
            logger.error(f"Chat error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': 'An unexpected error occurred. Please try again.'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


# ─── Session Endpoints ─────────────────────────────────────────────

@app.post("/sessions")
async def create_session_endpoint(req: SessionCreate):
    """Create a new empty session."""
    session_id = create_session(mode=req.mode)
    session = get_session(session_id)
    return session


@app.get("/sessions")
async def list_sessions():
    """List all sessions, newest first."""
    return get_sessions()


@app.get("/sessions/{session_id}")
async def get_session_endpoint(session_id: str):
    """Get a single session by ID."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/sessions/{session_id}/messages")
async def get_messages_endpoint(session_id: str):
    """Get all messages for a session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return get_session_messages(session_id)


@app.delete("/sessions/{session_id}")
async def delete_session_endpoint(session_id: str):
    """Delete a session and all its messages."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


# ─── Serve Frontend (local dev only) ──────────────────────────────

# Mount static files LAST so API routes take priority.
# On Vercel the frontend is served separately, so this is skipped gracefully.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    logger.info(f"Frontend directory not found at {FRONTEND_DIR} — skipping static mount (expected on Vercel)")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
