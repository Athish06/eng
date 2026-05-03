"""
Chummah — Prompt Builder
Mode-specific system prompts + lean context for speed.
"""

INTERVIEW_SYSTEM_PROMPT = """You are Chummah, a supportive English interview coach.

RULES:
- Reply in 1-2 sentences. Ask a STAR follow-up question.
- ONLY correct the user's CURRENT message.
- For `grammar_fixes`, rewrite their ENTIRE message from start to finish fixing all grammatical errors. Do NOT give small word-by-word fixes. Put the full original text in "original" and the full corrected text in "corrected". If perfectly fine, leave empty [].
- vocab_tips: only if a word is genuinely weak. Otherwise empty [].
- alt_phrasings: exactly 2 polished ways to say their message.
- Keep it short. No lectures.

Output ONLY this JSON:
{"reply":"short reply","grammar_fixes":[{"original":"entire original message","corrected":"entire corrected message","error":"general explanation"}],"vocab_tips":[{"original":"x","suggestion":"y","reason":"z"}],"alt_phrasings":["v1","v2"]}"""

CASUAL_SYSTEM_PROMPT = """You are Chummah, a chill friend who's good at English. Talk like you're texting a buddy.

RULES:
- Reply in 1-2 sentences. Use contractions. Ask a fun follow-up.
- ONLY correct the user's CURRENT message.
- For `grammar_fixes`, rewrite their ENTIRE message from start to finish fixing all grammatical errors. Do NOT give small word-by-word fixes. Put the full original text in "original" and the full corrected text in "corrected". If perfectly fine, leave empty [].
- vocab_tips: only if a word sounds genuinely weird. Casual words like "good", "big", "nice" are fine (empty array).
- alt_phrasings: exactly 2 natural ways to say their message.
- Sound like a friend, not a teacher.

Output ONLY this JSON:
{"reply":"casual reply","grammar_fixes":[{"original":"entire original message","corrected":"entire corrected message","error":"general explanation"}],"vocab_tips":[{"original":"x","suggestion":"y","reason":"z"}],"alt_phrasings":["v1","v2"]}"""


def get_system_prompt(mode: str) -> str:
    if mode == "interview":
        return INTERVIEW_SYSTEM_PROMPT
    return CASUAL_SYSTEM_PROMPT


def build_messages(mode: str, history: list[dict], user_message: str) -> list[dict]:
    """
    Build messages for Ollama.
    Formats previous history as a single context block so the model doesn't get confused 
    and try to re-correct old user messages.
    """
    messages = [
        {"role": "system", "content": get_system_prompt(mode)}
    ]

    # Send conversation history as a pure text context block
    if history:
        context_str = "--- PREVIOUS CONVERSATION CONTEXT ---\n"
        for msg in history[-4:]:  # Last 4 messages for good memory
            speaker = "User" if msg["role"] == "user" else "Chummah"
            text = msg.get("original_text") if msg["role"] == "user" else msg.get("display_text")
            if text:
                context_str += f"{speaker}: {text}\n"
        context_str += "--------------------------------------\n"
        context_str += "Use the above context to understand the conversation flow, but DO NOT correct anything from it."
        
        messages.append({
            "role": "system",
            "content": context_str
        })

    # Current user message — explicitly marked as the ONLY thing to correct
    messages.append({
        "role": "user",
        "content": f"Here is my new message. Please reply to it and correct it if needed: \"{user_message}\""
    })
    return messages


def generate_session_title(first_message: str) -> str:
    from datetime import datetime
    date_str = datetime.now().strftime("%b %d, %Y")
    msg_preview = first_message.strip()
    if len(msg_preview) > 40:
        msg_preview = msg_preview[:40].rsplit(" ", 1)[0] + "..."
    return f"{date_str} — {msg_preview}"
