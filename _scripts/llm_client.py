#!/usr/bin/env python3
"""Shared LLM client for all WSL cron pipelines.

老闆 directive 2026-10-22: route every cron pipeline through the **NVIDIA API**
(free tier) instead of MiniMax CN, after (a) MiniMax retired `MiniMax-M2`
(HTTP 404) and (b) the MiniMax CN balance ran out (HTTP 402 on every model).

Design:
  * Primary  : NVIDIA NIM  (OpenAI-compatible  POST {base}/chat/completions)
  * Fallback : MiniMax CN  (Anthropic-compatible POST {base}/v1/messages)

Both are read from env first, then ~/.hermes/.env, then ~/.hermes/config.yaml,
so the module works in cron (no shell env), in subprocesses, and interactively.

Usage:
    import sys; sys.path.insert(0, "/home/hermes/.hermes/lib")
    from llm_client import call_llm_text
    text = call_llm_text(system="You are…", user="Write…", max_tokens=8192)

Return value is a str on success, None on total failure. Never raises.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path("/home/hermes/.hermes/.env")
CONFIG_PATH = Path("/home/hermes/.hermes/config.yaml")

# NVIDIA: deepseek-v4.1-flash is a *reasoning* model — it emits reasoning_content
# next to the answer, so small max_tokens truncates the visible output.
DEFAULT_NVIDIA_MODEL = "deepseek-ai/deepseek-v4.1-flash"
DEFAULT_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

# MiniMax-M2 was retired; keep the current model as the fallback.
DEFAULT_MINIMAX_MODEL = "MiniMax-M3.1-Flash"
DEFAULT_MINIMAX_BASE = "https://api.minimaxi.com/anthropic"


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as exc:  # noqa: BLE001
        print(f"[llm_client] .env read failed: {exc}", file=sys.stderr)
    return out


def _nvidia_from_config() -> tuple[str, str]:
    """(api_key, base_url) from ~/.hermes/config.yaml providers.nvidia."""
    if not CONFIG_PATH.exists():
        return "", ""
    try:
        import yaml  # type: ignore
        cfg = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        p = (cfg.get("providers") or {}).get("nvidia") or {}
        return p.get("api_key") or "", p.get("base_url") or ""
    except Exception:  # noqa: BLE001
        return "", ""


def _creds() -> dict[str, str]:
    env = _read_env_file(ENV_PATH)
    cfg_key, cfg_base = _nvidia_from_config()
    return {
        "nv_key": os.environ.get("NVIDIA_API_KEY") or env.get("NVIDIA_API_KEY", "") or cfg_key,
        "nv_base": (os.environ.get("NVIDIA_BASE_URL")
                    or env.get("NVIDIA_BASE_URL", "")
                    or cfg_base
                    or DEFAULT_NVIDIA_BASE).rstrip("/"),
        "nv_model": (os.environ.get("RECIPE_NVIDIA_MODEL")
                     or env.get("RECIPE_NVIDIA_MODEL", "")
                     or DEFAULT_NVIDIA_MODEL),
        "mm_key": os.environ.get("MINIMAX_CN_API_KEY") or env.get("MINIMAX_CN_API_KEY", ""),
        "mm_base": (os.environ.get("MINIMAX_CN_BASE_URL")
                    or env.get("MINIMAX_CN_BASE_URL", "")
                    or DEFAULT_MINIMAX_BASE).rstrip("/"),
        "mm_model": (os.environ.get("RECIPE_LLM_MODEL")
                     or env.get("RECIPE_LLM_MODEL", "")
                     or DEFAULT_MINIMAX_MODEL),
    }


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> tuple[int, str]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def call_nvidia(messages: list[dict], max_tokens: int = 8192, temperature: float = 0.6,
                timeout: int = 420) -> str | None:
    """OpenAI-compatible chat completion via NVIDIA NIM.

    W97 (2026-10-23): `deepseek-ai/deepseek-v4.1-flash` is a *reasoning* model.
    It emits a `reasoning_content` trace that is charged against `max_tokens`
    before the answer starts, so a modest budget (3000) produced HTTP 200 with
    **empty `content`** — a silent failure that made every caller fall back to
    its regex/glossary path. Two changes fix it:

      * `max_tokens` default 8192 (room for trace + answer), and
      * `chat_template_kwargs={"thinking": False}` — measured 2s vs 15s and
        zero reasoning tokens, i.e. ~30x faster than the thinking default.

    The thinking-off payload is tried first; if the server rejects it (non-DeepSeek
    models, API change), the plain payload is retried before giving up.
    """
    c = _creds()
    if not c["nv_key"]:
        print("[llm_client] NVIDIA key not found", file=sys.stderr)
        return None

    base = {"model": c["nv_model"], "max_tokens": max_tokens,
            "temperature": temperature, "messages": messages}
    payloads = [
        {**base, "chat_template_kwargs": {"thinking": False}},
        base,
    ]
    for idx, payload in enumerate(payloads):
        status, body = _post_json(
            f"{c['nv_base']}/chat/completions", payload,
            {"Authorization": f"Bearer {c['nv_key']}"}, timeout,
        )
        if status != 200:
            print(f"[llm_client] NVIDIA HTTP {status} "
                  f"({'thinking-off' if idx == 0 else 'plain'}): {body[:200]}", file=sys.stderr)
            continue
        try:
            data = json.loads(body)
            msg = (data.get("choices") or [{}])[0].get("message", {})
            text = (msg.get("content") or "").strip()
            if text:
                return text
            print("[llm_client] NVIDIA empty content "
                  f"({'thinking-off' if idx == 0 else 'plain'}; "
                  f"reasoning={len(msg.get('reasoning_content') or '')}c)", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"[llm_client] NVIDIA parse failed: {exc}", file=sys.stderr)
    return None


def call_minimax(messages: list[dict], max_tokens: int = 8192,
                 timeout: int = 300) -> str | None:
    """Anthropic-compatible /v1/messages call to MiniMax CN."""
    c = _creds()
    if not c["mm_key"]:
        print("[llm_client] MiniMax key not found", file=sys.stderr)
        return None
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    convo = [m for m in messages if m.get("role") != "system"] or [{"role": "user", "content": ""}]
    status, body = _post_json(
        f"{c['mm_base']}/v1/messages",
        {"model": c["mm_model"], "max_tokens": max_tokens, "system": system, "messages": convo},
        {"Authorization": f"Bearer {c['mm_key']}", "anthropic-version": "2023-06-01"},
        timeout,
    )
    if status != 200:
        print(f"[llm_client] MiniMax HTTP {status}: {body[:200]}", file=sys.stderr)
        return None
    try:
        data = json.loads(body)
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return text or None
    except Exception as exc:  # noqa: BLE001
        print(f"[llm_client] MiniMax parse failed: {exc}", file=sys.stderr)
        return None


def call_llm_text(system: str, user: str, max_tokens: int = 8192,
                  temperature: float = 0.6, timeout: int = 420,
                  retries: int = 2, primary: str = "nvidia") -> str | None:
    """Generate text. NVIDIA first (default), MiniMax as fallback.

    primary="minimax" flips the order (useful once MiniMax is topped up).
    Returns None if every provider fails — callers decide what to do.
    """
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    order = ["nvidia", "minimax"] if primary != "minimax" else ["minimax", "nvidia"]
    for provider in order:
        for attempt in range(1, retries + 1):
            fn = call_nvidia if provider == "nvidia" else call_minimax
            text = fn(messages, max_tokens=max_tokens,
                      **({"temperature": temperature} if provider == "nvidia" else {}),
                      timeout=timeout)
            if text:
                print(f"[llm_client] {provider} ok (attempt {attempt})", file=sys.stderr)
                return text
            if attempt < retries:
                time.sleep(3)
        print(f"[llm_client] {provider} exhausted — next provider", file=sys.stderr)
    return None


if __name__ == "__main__":
    out = call_llm_text(system="Reply with the single word OK", user="ping")
    print("RESULT:", (out or "")[:200])
