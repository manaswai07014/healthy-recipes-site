#!/usr/bin/env python3
"""Shared hero-image generation for the research pipeline (W96, 2026-10-21).

Provider order: MiniMax image-01  →  Cloudflare Workers AI FLUX.1 [schnell].

Why: MiniMax CN hit `HTTP 402 insufficient_balance_error (1008)` and every
image call started failing. CF Workers AI is on the free plan (10,000
neurons/day; measured 172.8 neurons/image → ≈57 images/day) and this account
already has credentials in /home/hermes/.cfenv.

CF returns 1024x1024; we centre-crop to 16:9 to match the site invariant (P28).

Used by:
  _research/scripts/generate_hero_image.py
  _research/scripts/publish_to_site.py
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

MINIMAX_ENDPOINT = "https://api.minimaxi.com/v1/image_generation"
HERMES_ENV = Path("/home/hermes/.hermes/.env")
CFENV_PATH = Path("/home/hermes/.cfenv")
CF_ACCOUNT_ID = "b3e5ac003d206366f1a64379801164e2"
CF_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
MIN_BYTES = 50_000


def _read_kv(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def minimax_key() -> str:
    return os.environ.get("MINIMAX_CN_API_KEY") or _read_kv(HERMES_ENV, "MINIMAX_CN_API_KEY")


def cf_token() -> str:
    return os.environ.get("CF_API_TOKEN") or _read_kv(CFENV_PATH, "CF_API_TOKEN")


def _centre_crop_16x9(path: Path) -> None:
    try:
        from PIL import Image
    except ImportError:
        return  # site CSS uses object-fit:cover — cosmetic only
    with Image.open(path) as im:
        w, h = im.size
        target_h = int(w * 9 / 16)
        if h > target_h:
            top = (h - target_h) // 2
            im = im.crop((0, top, w, top + target_h))
        im.convert("RGB").save(path, "JPEG", quality=88)


def _try_minimax(prompt: str, out_path: Path):
    """Returns None on success, else an error string."""
    key = minimax_key()
    if not key:
        return "MINIMAX_CN_API_KEY not set"
    payload = json.dumps({
        "model": "image-01", "prompt": prompt,
        "aspect_ratio": "16:9", "n": 1,
    }).encode()
    req = urllib.request.Request(
        MINIMAX_ENDPOINT, data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}: {exc.read().decode()[:200]}"
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    urls = (data.get("data") or {}).get("image_urls") or []
    if not urls:
        return f"no image_urls: {json.dumps(data)[:200]}"
    try:
        with urllib.request.urlopen(urls[0], timeout=60) as img_resp:
            out_path.write_bytes(img_resp.read())
    except Exception as exc:  # noqa: BLE001
        return f"download failed: {exc}"
    return None


def _try_cf(prompt: str, out_path: Path):
    """Returns None on success, else an error string."""
    token = cf_token()
    if not token:
        return "CF_API_TOKEN unavailable (env or /home/hermes/.cfenv)"
    url = (f"https://api.cloudflare.com/client/v4/accounts/"
           f"{CF_ACCOUNT_ID}/ai/run/{CF_IMAGE_MODEL}")
    payload = json.dumps({"prompt": prompt[:2048], "steps": 4}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}: {exc.read().decode()[:200]}"
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    if not body.get("success"):
        return f"errors: {body.get('errors')}"
    b64 = (body.get("result") or {}).get("image")
    if not b64:
        return "no image data in response"
    out_path.write_bytes(base64.b64decode(b64))
    _centre_crop_16x9(out_path)
    return None


def generate(prompt: str, out_path: Path):
    """Generate a hero image. Returns (ok: bool, detail: str).

    detail is the winning provider name on success, or the combined error text.
    """
    if not prompt or len(prompt.strip()) < 10:
        return False, "prompt too short/empty"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    errors = []

    err = _try_minimax(prompt, out_path)
    if err is None and out_path.exists() and out_path.stat().st_size >= MIN_BYTES:
        return True, "minimax"
    errors.append(f"MiniMax: {err or 'output too small'}")
    out_path.unlink(missing_ok=True)

    err = _try_cf(prompt, out_path)
    if err is None and out_path.exists() and out_path.stat().st_size >= MIN_BYTES:
        return True, "cf-workers-ai"
    errors.append(f"CF Workers AI: {err or 'output too small'}")
    out_path.unlink(missing_ok=True)

    return False, " | ".join(errors)
