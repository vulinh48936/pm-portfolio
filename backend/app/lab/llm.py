"""Client for the in-house LLM (OpenAI-compatible `/chat/completions`).

Self-hosted only, with no cloud fallback. Configured in `backend/.env`:

    LLM_BASE_URL   API root, e.g. http://llm.internal:8000/v1  (required)
    LLM_MODEL      model name the server serves                (required)
    LLM_API_KEY    optional; many internal servers need none
    LLM_TIMEOUT    seconds, default 180

Without those two the calls raise a clear error; presets and hand-written code still
work, only Generate and free-form explanations are lost.
"""

from __future__ import annotations

import os
import re


_FENCE_RE = re.compile(r"^```(?:python|json)?\s*|\s*```$", re.MULTILINE)


def _cfg() -> tuple[str, str, str, float]:
    """(base_url, api_key, model, timeout); raises if required config is missing."""
    base = (os.environ.get("LLM_BASE_URL") or "").strip().rstrip("/")
    model = (os.environ.get("LLM_MODEL") or "").strip()
    if not base:
        raise RuntimeError("Chưa cấu hình LLM_BASE_URL trong backend/.env (LLM nội bộ).")
    if not model:
        raise RuntimeError("Chưa cấu hình LLM_MODEL trong backend/.env.")
    key = (os.environ.get("LLM_API_KEY") or "").strip()
    return base, key, model, float(os.environ.get("LLM_TIMEOUT", "180"))


def is_configured() -> bool:
    return bool((os.environ.get("LLM_BASE_URL") or "").strip()
                and (os.environ.get("LLM_MODEL") or "").strip())


def default_model() -> str:
    return _cfg()[2]


def strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = _FENCE_RE.sub("", text).strip()
    return text


def chat(prompt: str, model: str | None = None, temperature: float = 0.0) -> str:
    """One chat turn; network or HTTP failures become RuntimeError with a clear message."""
    import requests

    base, key, default, timeout = _cfg()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    messages = [{"role": "user", "content": prompt}]
    try:
        resp = requests.post(
            f"{base}/chat/completions", headers=headers,
            json={"model": model or default, "messages": messages,
                  "temperature": temperature, "stream": False},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Không kết nối được LLM tại {base}: {exc}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM trả HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"LLM error: {data['error']}")
    try:
        return data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"LLM trả response không đúng chuẩn OpenAI: {data}") from exc


def health() -> dict:
    """Ping `/models` for the Operations tab; never raises."""
    import requests

    if not is_configured():
        return {"ok": False, "base_url": os.environ.get("LLM_BASE_URL") or None,
                "model": os.environ.get("LLM_MODEL") or None,
                "detail": "Chưa cấu hình LLM_BASE_URL/LLM_MODEL"}
    base, key, model, _ = _cfg()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        r = requests.get(f"{base}/models", headers=headers, timeout=5)
        return {"ok": r.status_code < 400, "base_url": base, "model": model,
                "detail": None if r.status_code < 400 else f"HTTP {r.status_code}"}
    except Exception as exc:
        return {"ok": False, "base_url": base, "model": model, "detail": str(exc)}
