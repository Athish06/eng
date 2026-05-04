"""
Chummah — MongoDB Database Layer
Connects to MongoDB using 'eng' database.
Maintains the exact same synchronous API as the previous SQLite layer.
"""

import os
import logging
from datetime import datetime
from bson.objectid import ObjectId
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("chummah.db")

# ── Env-var lookup (case-insensitive for Vercel compatibility) ──────
def _get_mongo_url() -> str | None:
    """Look up MONGO_URL env var, trying several casings."""
    for key in ("MONGO_URL", "mongo_url", "Mongo_Url", "MONGODB_URI", "mongodb_uri"):
        val = os.environ.get(key)
        if val:
            return val
    return None

# ── Lazy client — created on first use, not at import time ──────────
_client = None
_db = None
_sessions_coll = None
_messages_coll = None


def _get_db():
    """Return (sessions_coll, messages_coll), creating the client lazily."""
    global _client, _db, _sessions_coll, _messages_coll
    if _client is None:
        mongo_url = _get_mongo_url()
        if not mongo_url:
            raise RuntimeError(
                "MongoDB connection URL not found. "
                "Set MONGO_URL (or mongo_url) in your environment / Vercel env vars."
            )
        from pymongo import MongoClient
        _client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        _db = _client["eng"]
        _sessions_coll = _db["sessions"]
        _messages_coll = _db["messages"]
    return _sessions_coll, _messages_coll


def _format_doc(doc: dict) -> dict:
    """Format MongoDB document to look like SQLite row."""
    if not doc:
        return doc
    if "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    if "session_id" in doc and isinstance(doc["session_id"], ObjectId):
        doc["session_id"] = str(doc["session_id"])
    return doc


def init_db():
    """Create indexes. Called at startup."""
    try:
        sessions_coll, messages_coll = _get_db()
        messages_coll.create_index("session_id")
        messages_coll.create_index("created_at")
        sessions_coll.create_index("created_at")
        logger.info("MongoDB indexes ensured.")
    except Exception as e:
        logger.error(f"init_db failed (non-fatal): {e}")


def create_session(mode: str = "casual", title: str | None = None) -> str:
    """Create a new chat session. Returns session ID string."""
    sessions_coll, _ = _get_db()
    if title is None:
        now = datetime.now().strftime("%b %d, %Y %I:%M %p")
        title = f"New Chat — {now}"

    doc = {
        "mode": mode,
        "title": title,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    result = sessions_coll.insert_one(doc)
    return str(result.inserted_id)


def update_session_title(session_id: str, title: str):
    """Update session title."""
    sessions_coll, _ = _get_db()
    sessions_coll.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"title": title}}
    )


def add_message(
    session_id: str,
    role: str,
    original_text: str | None = None,
    display_text: str | None = None,
    corrections: dict | None = None
) -> str:
    """Add a message to a session. Returns message ID string."""
    _, messages_coll = _get_db()
    doc = {
        "session_id": ObjectId(session_id),
        "role": role,
        "original_text": original_text,
        "display_text": display_text,
        "corrections": corrections,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    result = messages_coll.insert_one(doc)
    return str(result.inserted_id)


def get_sessions() -> list[dict]:
    """Get all sessions, newest first."""
    sessions_coll, _ = _get_db()
    pipeline = [
        {
            "$lookup": {
                "from": "messages",
                "localField": "_id",
                "foreignField": "session_id",
                "as": "messages"
            }
        },
        {
            "$addFields": {
                "message_count": {"$size": "$messages"}
            }
        },
        {
            "$project": {
                "messages": 0
            }
        },
        {
            "$sort": {"created_at": -1}
        }
    ]
    sessions = list(sessions_coll.aggregate(pipeline))
    return [_format_doc(s) for s in sessions]


def get_session(session_id: str) -> dict | None:
    """Get a single session by ID."""
    sessions_coll, _ = _get_db()
    try:
        session = sessions_coll.find_one({"_id": ObjectId(session_id)})
        return _format_doc(session) if session else None
    except Exception:
        return None


def get_session_messages(session_id: str) -> list[dict]:
    """Get all messages for a session, oldest first."""
    _, messages_coll = _get_db()
    try:
        messages = list(messages_coll.find({"session_id": ObjectId(session_id)}).sort("created_at", 1))
        return [_format_doc(m) for m in messages]
    except Exception:
        return []


def get_recent_messages(session_id: str, limit: int = 6) -> list[dict]:
    """Get the last N messages for context window."""
    _, messages_coll = _get_db()
    try:
        # Get last N messages (newest first)
        messages = list(messages_coll.find({"session_id": ObjectId(session_id)})
                        .sort("created_at", -1)
                        .limit(limit))
        # Reverse to get oldest first
        messages.reverse()
        return [_format_doc(m) for m in messages]
    except Exception:
        return []


def delete_session(session_id: str):
    """Delete a session and all its messages."""
    sessions_coll, messages_coll = _get_db()
    try:
        messages_coll.delete_many({"session_id": ObjectId(session_id)})
        sessions_coll.delete_one({"_id": ObjectId(session_id)})
    except Exception:
        pass


def get_session_count() -> int:
    """Get total number of sessions."""
    sessions_coll, _ = _get_db()
    return sessions_coll.count_documents({})
