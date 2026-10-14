"""Minimal Gemini REST client for structured JSON responses."""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
REQUEST_TIMEOUT_SECONDS = 60

# Retry policy per Google's Gemini API troubleshooting guide: retry only transient
# errors with exponential backoff plus jitter, starting at ~1s and doubling.
# https://ai.google.dev/gemini-api/docs/troubleshooting
RETRYABLE_STATUS_CODES = (408, 429, 500, 502, 503, 504)
RETRY_INITIAL_DELAY_SECONDS = 1.0
RETRY_EXP_BASE = 2
# Google advises starting with a low retry count for latency-sensitive calls; this
# endpoint is on the synchronous analyze path, so cap total attempts at 3 (~1s + ~2s).
RETRY_ATTEMPTS = 3


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_local_env()


def is_configured() -> bool:
    return _api_key() is not None


def _api_key() -> str | None:
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key.startswith("AIza"):
        return None
    # A key pasted twice back-to-back is a common copy error; recover the single key.
    if key.count("AIza") == 2:
        half = len(key) // 2
        if key[:half] == key[half:]:
            return key[:half]
        return None
    if key.count("AIza") > 2:
        return None
    return key


def generate_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    api_key = _api_key()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing or malformed. Use a single Google API key in .env."
        )

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    url = f"{DEFAULT_BASE_URL}/models/{model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.25,
            "responseMimeType": "application/json",
        },
    }
    body = _post_with_retry(url, api_key, payload)

    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text.strip():
        raise RuntimeError("Gemini returned empty text")

    return _parse_json_text(text)


def _post_with_retry(url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to Gemini, retrying only the transient statuses Google documents."""
    last_error: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.post(
                url,
                params={"key": api_key},
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            last_error = exc
        else:
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response.json()
            last_error = requests.HTTPError(
                f"{response.status_code} from Gemini: {response.text[:200]}",
                response=response,
            )

        if attempt < RETRY_ATTEMPTS - 1:
            delay = RETRY_INITIAL_DELAY_SECONDS * (RETRY_EXP_BASE**attempt)
            time.sleep(delay + random.uniform(0, 1))  # jitter, per Google's guidance

    raise last_error if last_error else RuntimeError("Gemini request failed")


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini JSON response must be an object")
    return parsed
