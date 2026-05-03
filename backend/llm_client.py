"""
Chummah — LLM Client (Groq)
Handles communication with Groq API.
Supports streaming (for ChatGPT-like UX) and full response modes.
"""

import os
import httpx
import json
import re
import logging
from typing import AsyncGenerator
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("chummah.llm")

# --- Groq Configuration ---
GROQ_API_KEY = os.environ.get("groq_api_key")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"  # Extremely fast and smart

if not GROQ_API_KEY:
    logger.error("groq_api_key not found in .env file!")


async def check_health() -> dict:
    """Check if Groq API key is configured."""
    return {
        "status": "ok" if GROQ_API_KEY else "error",
        "active_model": GROQ_MODEL if GROQ_API_KEY else "Missing API Key"
    }


async def stream_chat(messages: list[dict], model: str | None = None) -> AsyncGenerator[str, None]:
    """Stream chat using Groq API."""
    if not GROQ_API_KEY:
        yield '{"error": "Groq API key not configured in .env"}'
        return

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "stream": True,
        "temperature": 0.65,
        "max_tokens": 400,
        "response_format": {"type": "json_object"}
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        async with client.stream(
            "POST",
            f"{GROQ_BASE_URL}/chat/completions",
            json=payload,
            headers=headers
        ) as response:
            if response.status_code != 200:
                err_text = await response.aread()
                logger.error(f"Groq API error: {response.status_code} {err_text}")
                yield f'{{"error": "Groq API Error: {response.status_code}"}}'
                return
                
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except json.JSONDecodeError:
                        continue


def parse_response_json(raw_content: str) -> dict:
    content = raw_content.strip()

    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*\n?", "", content)
        content = re.sub(r"\n?```\s*$", "", content)

    try:
        result = json.loads(content)
        return normalize_response(result)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        try:
            result = json.loads(json_match.group())
            return normalize_response(result)
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse response as JSON, using raw text")
    return {
        "reply": content,
        "grammar_fixes": [],
        "vocab_tips": [],
        "alt_phrasings": []
    }


def normalize_response(data: dict) -> dict:
    return {
        "reply": data.get("reply", data.get("response", "")),
        "grammar_fixes": data.get("grammar_fixes", []),
        "vocab_tips": data.get("vocab_tips", []),
        "alt_phrasings": data.get("alt_phrasings", [])
    }
