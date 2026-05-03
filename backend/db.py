"""
Chummah — MongoDB Database Layer
Connects to MongoDB using 'eng' database.
Maintains the exact same synchronous API as the previous SQLite layer.
"""

import os
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.environ.get("mongo_url")
if not MONGO_URL:
    raise ValueError("mongo_url not found in .env")

# Connect to MongoDB
client = MongoClient(MONGO_URL)
db = client["eng"]
sessions_coll = db["sessions"]
messages_coll = db["messages"]


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
    """Create indexes."""
    messages_coll.create_index("session_id")
    messages_coll.create_index("created_at")
    sessions_coll.create_index("created_at")


def create_session(mode: str = "casual", title: str | None = None) -> str:
    """Create a new chat session. Returns session ID string."""
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
    try:
        session = sessions_coll.find_one({"_id": ObjectId(session_id)})
        return _format_doc(session) if session else None
    except Exception:
        return None


def get_session_messages(session_id: str) -> list[dict]:
    """Get all messages for a session, oldest first."""
    try:
        messages = list(messages_coll.find({"session_id": ObjectId(session_id)}).sort("created_at", 1))
        return [_format_doc(m) for m in messages]
    except Exception:
        return []


def get_recent_messages(session_id: str, limit: int = 6) -> list[dict]:
    """Get the last N messages for context window."""
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
    try:
        messages_coll.delete_many({"session_id": ObjectId(session_id)})
        sessions_coll.delete_one({"_id": ObjectId(session_id)})
    except Exception:
        pass


def get_session_count() -> int:
    """Get total number of sessions."""
    return sessions_coll.count_documents({})
