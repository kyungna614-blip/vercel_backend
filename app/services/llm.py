"""
Unified LLM client — tries Groq first (fast + free), falls back to Anthropic.
All AI calls in the app go through `llm_generate()`.
"""
from __future__ import annotations

import json
import re
from typing import Union

from app.config import settings


def llm_generate(prompt: str, max_tokens: int = 2500, temperature: float = 0.7) -> str:
    """
    Send a prompt to the best available LLM and return the raw text response.
    Priority: Groq (fast, free tier) → Anthropic (paid).
    Raises RuntimeError if no LLM is available.
    """
    errors = []

    # ── 1. Try Groq ──────────────────────────────────────────────────────────
    if settings.GROQ_API_KEY:
        try:
            from groq import Groq  # type: ignore[import-untyped]
            client = Groq(api_key=settings.GROQ_API_KEY)
            chat = client.chat.completions.create(
                model=settings.AI_MODEL if settings.AI_PROVIDER == "groq" else "llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return chat.choices[0].message.content.strip()
        except Exception as e:
            errors.append(f"Groq: {e}")

    # ── 2. Try Anthropic ─────────────────────────────────────────────────────
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic  # type: ignore[import-untyped]
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=settings.AI_MODEL if settings.AI_PROVIDER == "anthropic" else "claude-3-5-sonnet-20241022",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            errors.append(f"Anthropic: {e}")

    raise RuntimeError(f"No LLM available. Errors: {'; '.join(errors)}")


def llm_generate_json(prompt: str, max_tokens: int = 2500) -> Union[dict, list]:
    """
    Call LLM and parse the response as JSON.
    Handles markdown code fences and partial JSON extraction.
    """
    raw = llm_generate(prompt, max_tokens=max_tokens)
    # Strip markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try extracting array
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        # Try extracting object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse LLM JSON output: {cleaned[:300]}")
