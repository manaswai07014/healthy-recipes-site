"""
Healthy Western Recipes — Recipe Generator Pipeline

Mirrors the CarMotion Daily news_to_website.py pattern:
- Cron-driven (intended for daily execution)
- LLM-powered recipe generation (MiniMax-M2 primary, regex fallback)
- Output: YAML front matter + Markdown body in Jekyll _recipes/ format
- Strict 7-day rolling dedup by slug

Usage:
    python3 generate_recipe.py [--count N] [--dry-run]

Environment:
    MINIMAX_CN_API_KEY / MINIMAX_CN_BASE_URL  (required for LLM path)
"""

from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RECIPES_DIR = ROOT / "_recipes"
ASSETS_DIR = ROOT / "assets" / "recipes"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = Path.home() / "healthy-recipes-logs"
LOG_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# LLM config (CarMotion-style: MiniMax CN primary, regex fallback)
# ---------------------------------------------------------------------------
LLM_ENDPOINT = os.environ.get("MINIMAX_CN_BASE_URL", "https://api.minimaxi.com/anthropic")
LLM_API_KEY = os.environ.get("MINIMAX_CN_API_KEY", "")

# W83: Auto-source /home/hermes/.hermes/.env if key still missing.
# Direct python invocations don't inherit shell env vars, but the .env file
# always has the canonical keys. This avoids silent "regex mode" fallbacks.
if not LLM_API_KEY:
    env_path = Path("/home/hermes/.hermes/.env")
    if env_path.exists():
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    # Don't override what's already set, but DO load missing keys
                    if k == "MINIMAX_CN_API_KEY" and not os.environ.get(k):
                        os.environ[k] = v
                        LLM_API_KEY = v
                    elif k == "MINIMAX_CN_BASE_URL" and not os.environ.get(k):
                        os.environ[k] = v
                        LLM_ENDPOINT = v
        except Exception as e:
            print(f"[WARN] Failed to source .env: {e}", file=sys.stderr)
# W97 (2026-10-21): MiniMax-M2 was retired (HTTP 404 "no longer available") AND
# the MiniMax CN balance ran out (HTTP 402 on every other model). Default to the
# current model, and add an NVIDIA NIM text fallback (free tier, key already in
# .env) so the daily pipeline cannot be zeroed out by either failure again.
LLM_MODEL = os.environ.get("RECIPE_LLM_MODEL", "MiniMax-M3.1-Flash")

# NVIDIA NIM fallback (OpenAI-compatible chat completions)
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_ENDPOINT = os.environ.get(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
NVIDIA_MODEL = os.environ.get("RECIPE_NVIDIA_MODEL", "deepseek-ai/deepseek-v4.1-flash")

if not NVIDIA_API_KEY:
    _nv_env = Path("/home/hermes/.hermes/.env")
    if _nv_env.exists():
        try:
            for _line in _nv_env.read_text().splitlines():
                _line = _line.strip()
                if _line.startswith("NVIDIA_API_KEY="):
                    NVIDIA_API_KEY = _line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["NVIDIA_API_KEY"] = NVIDIA_API_KEY
                    break
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] Failed to source NVIDIA_API_KEY: {e}", file=sys.stderr)

# MiniMax image gen endpoint (separate from LLM endpoint)
IMAGE_GEN_URL = "https://api.minimaxi.com/v1/image_generation"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_CALORIES = 400
MAX_CALORIES = 600
MIN_PROTEIN = 15
RECIPE_BODY_MIN_WORDS = 600
RECIPE_BODY_TARGET_WORDS = 1000
MAX_DAYS_BACK = 7

# ---------------------------------------------------------------------------
# Recipe prompt — the Michelin chef angle
# ---------------------------------------------------------------------------
RECIPE_SYSTEM_PROMPT = """You are a Michelin-starred chef who specializes in healthy Mediterranean and Western cuisine.
You are also an expert food blogger with deep knowledge of SEO.
You create low-calorie recipes (400-600 kcal per serving) that are at least 15g protein, delicious, and achievable on a weeknight.

Always write in English. Never use clichés like "easy", "simple", or "delicious" without backing them up.
Focus on specific technique, sensory detail (sounds, aromas, textures), and practical timing.
Never claim originality — every recipe is developed in-house by our editorial kitchen, drawing on Mediterranean and Western culinary traditions, and adapted for a healthy lifestyle."""


RECIPE_USER_PROMPT = """Create an original, low-calorie Mediterranean or Western recipe using the following core theme/ingredient.

CORE THEME: {theme}

CONSTRAINTS (these are non-negotiable):
- Each serving: 400-600 kcal (calculate accurately)
- Each serving: at least 15g protein
- Total time: under 60 minutes
- Servings: 2-4 people
- All ingredients must be available in a Western supermarket
- No raw/undercooked animal products; cook chicken to 75°C internal, pork to 70°C, fish to 63°C

OUTPUT FORMAT (strict JSON, no markdown, no commentary):
{{
  "seo_title": "Recipe name (50-70 chars, include 1-2 search-intent keywords e.g. 'Easy 30-Minute Mediterranean Cod')",
  "meta_description": "Description with long-tail keyword phrases (80-120 chars, answer question format)",
  "keywords": "5-8 long-tail search phrases (comma-separated) e.g. 'easy mediterranean cod recipe, low calorie cod dinner, baked cod with tomatoes'",
  "recipe_name": "Full recipe name (descriptive with modifier)",
  "cuisine": "Italian | Mediterranean | French | Spanish | Greek | European | American",
  "category": "Main | Soup | Salad | Side | Breakfast",
  "diet_tags": ["Low-Calorie", "High-Protein", "Quick", "Mediterranean", ...],
  "prep_time_mins": <int>,
  "cook_time_mins": <int>,
  "total_time_mins": <int>,
  "servings": <int>,
  "introduction": "150-char intro with sensory detail and technique note",
  "ingredients_api_format": [
    "<qty> <unit> <english name> (<chinese name>)",
    "<qty> <unit> <english name> (<chinese name>)",
    ...
  ],
  "ingredients_display": [
    "Friendly display name with qty",
    ...
  ],
  "instructions": [
    "Step 1: detailed step with sensory detail, timing, what to look for",
    ...
  ],
  "chef_tips": "1-2 paragraphs on technique variations, swaps, storage",
  "image_prompt": "Overhead shot, gourmet plating, rustic wooden table, bright natural kitchen light, shallow depth of field, focused on <dish> --ar 16:9",
  "nutrition_per_serving": {{
    "calories": <int>,
    "protein_g": <int>,
    "carbs_g": <int>,
    "fat_g": <int>,
    "fiber_g": <int>
  }}
}}

CRITICAL: Output ONLY valid JSON. No markdown fences. No preamble."""


# ---------------------------------------------------------------------------
# Theme rotation — produces diverse content
# ---------------------------------------------------------------------------
THEME_BANK = [
    "Greek lemon chicken souvlaki with tzatziki",
    "Spanish garlic shrimp (gambas al ajillo)",
    "Italian seafood pasta with white wine",
    "Provençal fish stew with fennel and saffron",
    "Tuscan white bean and kale soup (ribollita)",
    "Moroccan-spiced roasted cauliflower with tahini",
    "Greek horiatiki salad with grilled halloumi",
    "French ratatouille with herbed goat cheese",
    "Spanish chickpea and spinach stew",
    "Italian stuffed bell peppers with ground turkey",
    "Lemon herb salmon with asparagus",
    "Mediterranean tuna and white bean salad",
    "Turkish lentil soup with mint",
    "Greek spanakorizo (spinach rice)",
    "Italian minestrone with pesto swirl",
    "Provençal daube of beef with mushrooms",
    "Spanish romesco sauce with grilled vegetables",
    "Greek avgolemono (lemon chicken soup)",
    "Italian osso buco with gremolata",
    "French salmon en papillote with herbs",
    "Spanish paella with chicken and seafood",
    # Expanded 2026-09-02 based on category research (broad low-calorie/Mediterranean
    # patterns observed across multiple recipe publications — see skill healthy-recipes-site
    # P28: 'Topic diversity expansion'. No specific recipes or URLs referenced.)
    "One-skillet salmon with garlicky broccoli",
    "Sheet-pan shrimp with pineapple and peppers",
    "Quinoa bowl with feta, olives and tomatoes",
    "Lentil and lamb burgers with tzatziki",
    "Vegetarian sushi grain bowl with edamame",
    "Turkey and black bean enchilada skillet",
    "Chicken fajita bowl with cauliflower rice",
    "Miso-glazed cod with sesame greens",
    "Thai-style chicken lettuce wraps with lime",
    "Moroccan chickpea and sweet potato tagine",
    "Vietnamese-style chicken pho with zucchini noodles",
    "Tofu and vegetable stir-fry with ginger-scallion sauce",
    "Greek moussaka with lamb and eggplant",
    "Italian cacio e pepe with green peas",
    "Moroccan tagine of chicken with preserved lemon",
    "French chicken chasseur (hunter-style)",
    # W98 (2026-10-23): breakfast gap fill. Category audit showed Main 110 /
    # Soup 12 / Side 1 / Salad 1 / Breakfast 0 — the bank had zero breakfast
    # themes, so the daily picker could never produce one. All eight are
    # Mediterranean/Western, egg- or dairy-led for protein, and can land in the
    # 400-600 kcal band.
    "Mediterranean shakshuka with feta and chickpeas",
    "Greek yogurt bowl with berries, walnuts and honey",
    "Spinach and feta omelette with sourdough toast",
    "Turkish menemen with eggs, peppers and feta",
    "High-protein cottage cheese pancakes with berries",
    "Avocado toast with poached eggs and za'atar",
    "Baked eggs with spinach, tomato and feta",
    "Quinoa breakfast bowl with yogurt and toasted almonds",
    "Spanish albondigas (turkey meatballs) in tomato sauce",
    "Greek gemista (stuffed tomatoes and peppers)",
    "Italian pesto-crusted cod with green beans",
    "French soupe au pistou",
    "Spanish pulpo a la gallega (Galician octopus)",
    # P70 (2026-09-08): Expanded theme bank with 9 NEW low-cal Mediterranean themes
    # from EatingWell 22-recipe roundup. Each theme introduces a NEW protein we have
    # not published yet (existing proteins: chicken x5, salmon x3, tofu, turkey, etc.).
    # All themes comply with P26 hard rule: <30 min, <575 kcal, ≥15g protein.
    "Stuffed pepper casserole with ground beef and smoked paprika",
    "Greek-inspired lamb burgers with herb-feta yogurt sauce",
    "Pistachio-crusted halibut with lemon and herbs",
    "Prosciutto pizza with corn, arugula, and shaved parmesan",
    "Baked mahi-mahi with garlic-herb butter and lemon slices",
    "Scallops with lemon-basil sauce over zucchini noodles",
    "Sheet-pan halibut with cherry tomatoes and olives",
    "Low-carb ground turkey zucchini boats with smoked paprika",
    "One-pot whole-wheat pasta with spinach and cherry tomatoes",
    # W83 (2026-09-13): New themes targeting underused proteins (cod, tuna,
    # scallops, lentil, mussels, clams, sardines, mackerel, swordfish, trout,
    # sea bass). All <30 min, 400-575 kcal, ≥15g protein. Sources researched:
    # Mediterranean baked cod 332-485 kcal/32g, tuna salad 275 kcal/29g,
    # lemon-garlic seared scallops 285 kcal/42g.
    "Mediterranean baked cod with tomatoes capers and olives",
    "Lemon-herb seared scallops over zucchini noodles",
    "Greek yogurt Mediterranean tuna salad with cucumber and olives",
    "Turkish red lentil soup with mint and lemon",
    "Mussels marinara over whole-wheat linguine",
    "Sardine and white bean salad with lemon vinaigrette",
    "Pan-seared mackerel with fennel and orange salad",
    "Swordfish piccata with lemon-caper sauce",
    "Whole-wheat pasta with clams and white wine",
    "Trout al cartoccio with herbs and cherry tomatoes",
    "Roasted sea bass with fennel capers and lemon",
    "Three-bean Mediterranean salad with tuna",
    "Lemon-cod foil packets with spinach and pine nuts",
    "White bean and sardine toast with lemon and parsley",
    "Sicilian swordfish rolls with pine nuts and raisins",
]


def pick_theme(recent_titles: list[str]) -> str:
    """Pick a theme that hasn't appeared in recent titles."""
    candidates = [
        t for t in THEME_BANK
        if not any(word.lower() in r.lower() for r in recent_titles for word in t.split()[:3])
    ]
    return candidates[0] if candidates else THEME_BANK[0]


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------
SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return SLUG_RE.sub("-", text.lower()).strip("-")


def load_recent_slugs(days: int = MAX_DAYS_BACK) -> set[str]:
    """Return set of slugs from recipes published in last N days."""
    if not RECIPES_DIR.exists():
        return set()
    cutoff = datetime.now() - timedelta(days=days)
    slugs: set[str] = set()
    for f in RECIPES_DIR.glob("*.md"):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$", f.name)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y-%m-%d")
            if d >= cutoff:
                slugs.add(m.group(2))
        except ValueError:
            continue
    return slugs


def load_recent_titles(days: int = MAX_DAYS_BACK) -> list[str]:
    titles: list[str] = []
    if not RECIPES_DIR.exists():
        return titles
    cutoff = datetime.now() - timedelta(days=days)
    for f in RECIPES_DIR.glob("*.md"):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$", f.name)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y-%m-%d")
            if d >= cutoff:
                # Read first H1 line as title
                text = f.read_text(encoding="utf-8")
                title_m = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
                if title_m:
                    titles.append(title_m.group(1).strip().strip('"').strip("'"))
        except ValueError:
            continue
    return titles


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------
def _call_llm_minimax(theme: str, max_retries: int = 2) -> Optional[dict]:
    """Call MiniMax via the Anthropic-compatible /v1/messages endpoint."""
    if not LLM_API_KEY:
        print("[LLM] MINIMAX_CN_API_KEY not set — falling back to regex mode", file=sys.stderr)
        return None

    prompt = RECIPE_USER_PROMPT.format(theme=theme)
    payload = {
        "model": LLM_MODEL,
        "max_tokens": 4096,
        "system": RECIPE_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                LLM_ENDPOINT.rstrip("/") + "/v1/messages",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": LLM_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
            # Anthropic Messages API returns content[0].text
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            # Strip markdown fences if any leaked
            text = re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = re.sub(r"\s*```$", "", text.strip())
            recipe = json.loads(text)

            # Validate critical fields
            required = ["recipe_name", "seo_title", "meta_description",
                       "ingredients_api_format", "ingredients_display",
                       "instructions", "nutrition_per_serving"]
            for k in required:
                if k not in recipe:
                    raise ValueError(f"missing required field: {k}")

            # Calorie gate
            cal = recipe.get("nutrition_per_serving", {}).get("calories", 0)
            if not (MIN_CALORIES <= cal <= MAX_CALORIES):
                raise ValueError(f"calories {cal} out of range [{MIN_CALORIES}, {MAX_CALORIES}]")
            pro = recipe.get("nutrition_per_serving", {}).get("protein_g", 0)
            if pro < MIN_PROTEIN:
                raise ValueError(f"protein {pro}g below minimum {MIN_PROTEIN}g")

            return recipe

        except urllib.error.HTTPError as e:
            print(f"[LLM] HTTP {e.code} attempt {attempt}: {e.read().decode()[:]}", file=sys.stderr)
            if e.code == 429:
                time.sleep(60)  # quota backoff
            else:
                time.sleep(5)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[LLM] parse/validation error attempt {attempt}: {e}", file=sys.stderr)
            time.sleep(2)
        except Exception as e:
            print(f"[LLM] error attempt {attempt}: {e}", file=sys.stderr)
            time.sleep(5)

    return None


def _validate_recipe(recipe: dict) -> dict:
    """Shared validation for any provider's output. Raises ValueError."""
    required = ["recipe_name", "seo_title", "meta_description",
                "ingredients_api_format", "ingredients_display",
                "instructions", "nutrition_per_serving"]
    for k in required:
        if k not in recipe:
            raise ValueError(f"missing required field: {k}")
    nutrition = recipe.get("nutrition_per_serving", {}) or {}
    cal = nutrition.get("calories", 0)
    try:
        cal = float(cal)
    except (TypeError, ValueError):
        raise ValueError(f"calories not numeric: {cal!r}")
    if not (MIN_CALORIES <= cal <= MAX_CALORIES):
        raise ValueError(f"calories {cal} out of range [{MIN_CALORIES}, {MAX_CALORIES}]")
    pro = nutrition.get("protein_g", 0)
    try:
        pro = float(pro)
    except (TypeError, ValueError):
        raise ValueError(f"protein not numeric: {pro!r}")
    if pro < MIN_PROTEIN:
        raise ValueError(f"protein {pro}g below minimum {MIN_PROTEIN}g")
    return recipe


def _extract_json(text: str) -> dict:
    """Strip markdown fences and parse the first JSON object."""
    text = re.sub(r"^```(?:json)?\s*", "", (text or "").strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def _call_llm_nvidia(theme: str, max_retries: int = 2) -> Optional[dict]:
    """W97: NVIDIA NIM fallback (OpenAI-compatible chat completions)."""
    if not NVIDIA_API_KEY:
        print("[LLM-NVIDIA] NVIDIA_API_KEY not set — cannot use fallback", file=sys.stderr)
        return None

    prompt = RECIPE_USER_PROMPT.format(theme=theme)
    payload = {
        "model": NVIDIA_MODEL,
        # 4096 was not enough: deepseek-v4.1-flash also emits reasoning_content,
        # so the visible JSON got truncated mid-string ("Unterminated string").
        "max_tokens": 8192,
        "temperature": 0.6,
        "messages": [
            {"role": "system", "content": RECIPE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                NVIDIA_ENDPOINT,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {NVIDIA_API_KEY}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=420) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
            choices = data.get("choices") or []
            if not choices:
                raise ValueError(f"no choices in response: {json.dumps(data)[:200]}")
            text = choices[0].get("message", {}).get("content", "")
            recipe = _extract_json(text)
            return _validate_recipe(recipe)
        except urllib.error.HTTPError as e:
            print(f"[LLM-NVIDIA] HTTP {e.code} attempt {attempt}: {e.read().decode()[:200]}",
                  file=sys.stderr)
            time.sleep(60 if e.code == 429 else 5)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[LLM-NVIDIA] parse/validation error attempt {attempt}: {e}", file=sys.stderr)
            time.sleep(2)
        except Exception as e:  # noqa: BLE001
            print(f"[LLM-NVIDIA] error attempt {attempt}: {e}", file=sys.stderr)
            time.sleep(5)

    return None


def call_llm(theme: str, max_retries: int = 2) -> Optional[dict]:
    """Generate recipe JSON. MiniMax first, then NVIDIA NIM (W97: free fallback).

    Returns dict or None. Never raises — the caller treats None as "skip run".
    """
    recipe = _call_llm_minimax(theme, max_retries)
    if recipe:
        return recipe
    print("[LLM] MiniMax unavailable — trying NVIDIA NIM fallback", file=sys.stderr)
    recipe = _call_llm_nvidia(theme, max_retries)
    if recipe:
        print(f"[LLM] NVIDIA fallback succeeded ({NVIDIA_MODEL})", file=sys.stderr)
    return recipe


# ---------------------------------------------------------------------------
# Hero image generation (P45 inline atomic step — 2026-09-04 惠惠)
#
# MUST be called immediately after render_recipe_markdown(), BEFORE
# write_text(). If image gen raises, do NOT write the .md file → cron abort,
# broken frontmatter never enters working tree.
#
# Uses MiniMax image-01 (https://api.minimaxi.com/v1/image_generation).
# Output: 1280×720 JPEG (~300KB), 16:9 ratio (P28 invariant).
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# W96 (2026-10-21): Cloudflare Workers AI fallback for hero images.
#
# MiniMax CN hit HTTP 402 insufficient_balance_error and the pipeline started
# failing. CF Workers AI serves FLUX.1 [schnell] on the free plan
# (10,000 neurons/day ≈ 230 images — the daily pipeline needs 2), and this
# account already has credentials in /home/hermes/.cfenv.
# CF returns 1024x1024; we centre-crop to the site's 16:9 invariant (P28).
# ---------------------------------------------------------------------------
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "b3e5ac003d206366f1a64379801164e2")
CF_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
CFENV_PATH = Path("/home/hermes/.cfenv")


def _load_cf_token() -> str:
    """CF API token from the environment, else /home/hermes/.cfenv."""
    tok = os.environ.get("CF_API_TOKEN", "")
    if tok:
        return tok
    if CFENV_PATH.exists():
        for line in CFENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("CF_API_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _centre_crop_16x9(path: Path) -> None:
    """Centre-crop an image to 16:9 in place (CF returns 1:1)."""
    try:
        from PIL import Image
    except ImportError:
        return  # site CSS uses object-fit:cover, so this is cosmetic only
    with Image.open(path) as im:
        w, h = im.size
        target_h = int(w * 9 / 16)
        if h > target_h:
            top = (h - target_h) // 2
            im = im.crop((0, top, w, top + target_h))
        im.convert("RGB").save(path, "JPEG", quality=88)


def _generate_hero_image_cf(image_prompt: str, out_path: Path) -> None:
    """Generate via Cloudflare Workers AI FLUX.1-schnell; writes out_path or raises."""
    import base64
    token = _load_cf_token()
    if not token:
        raise RuntimeError("CF_API_TOKEN unavailable (env or /home/hermes/.cfenv)")
    url = (f"https://api.cloudflare.com/client/v4/accounts/"
           f"{CF_ACCOUNT_ID}/ai/run/{CF_IMAGE_MODEL}")
    payload = json.dumps({"prompt": image_prompt[:2048], "steps": 4}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("success"):
        raise RuntimeError(f"CF Workers AI error: {body.get('errors')}")
    b64 = (body.get("result") or {}).get("image")
    if not b64:
        raise RuntimeError("CF Workers AI returned no image data")
    out_path.write_bytes(base64.b64decode(b64))
    _centre_crop_16x9(out_path)
    print(f"  🖼  Hero image (CF Workers AI FLUX): {out_path} ({out_path.stat().st_size} bytes)")


def generate_hero_image(slug: str, image_prompt: str) -> Path:
    """Generate hero image and save to assets/recipes/{slug}.jpg.

    Provider order: MiniMax image-01 → Cloudflare Workers AI FLUX.1-schnell.
    Returns the saved Path. Raises on any failure (no silent fallback, P45).
    """
    if not image_prompt or len(image_prompt.strip()) < 10:
        raise ValueError(f"image_prompt too short/empty: {image_prompt!r}")

    out_path = ASSETS_DIR / f"{slug}.jpg"
    errors = []

    # --- Attempt 1: MiniMax image-01 ---
    if LLM_API_KEY:
        try:
            payload = json.dumps({
                "model": "image-01",
                "prompt": image_prompt,
                "aspect_ratio": "16:9",
                "n": 1,
                "response_format": "url",
            }).encode("utf-8")
            req = urllib.request.Request(
                IMAGE_GEN_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("base_resp", {}).get("status_code") != 0:
                raise RuntimeError(f"MiniMax non-zero status: {body.get('base_resp')}")
            image_urls = body.get("data", {}).get("image_urls") or []
            if not image_urls:
                raise RuntimeError("MiniMax returned no image URLs")
            with urllib.request.urlopen(image_urls[0], timeout=60) as img_resp:
                out_path.write_bytes(img_resp.read())
            print(f"  🖼  Hero image (MiniMax): {out_path} ({out_path.stat().st_size} bytes)")
        except Exception as exc:  # noqa: BLE001 — fall through to CF
            errors.append(f"MiniMax: {exc}")
    else:
        errors.append("MiniMax: MINIMAX_CN_API_KEY not set")

    # --- Attempt 2: Cloudflare Workers AI (fallback) ---
    if not out_path.exists() or out_path.stat().st_size < 50_000:
        try:
            _generate_hero_image_cf(image_prompt, out_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"CF Workers AI: {exc}")

    # --- Shared sanity gate (P45: fail fast, never commit a broken asset) ---
    if not out_path.exists():
        raise RuntimeError("hero image generation failed — " + " | ".join(errors))
    if out_path.stat().st_size < 50_000:
        size = out_path.stat().st_size
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"hero image too small ({size} bytes) — " + " | ".join(errors))
    with open(out_path, "rb") as fh:
        magic = fh.read(3)
    if magic != b"\xff\xd8\xff":
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"hero image not JPEG (magic={magic!r}) — " + " | ".join(errors))

    return out_path


# ---------------------------------------------------------------------------
# Recipe → Markdown
# ---------------------------------------------------------------------------
def yaml_quote(value) -> str:
    """Safely quote a scalar for YAML frontmatter.

    W96 (2026-10-21): these values were interpolated raw, so any LLM-generated
    title / meta_description containing ': ' produced invalid YAML. Jekyll then
    failed to load the document, its permalink fell back to the build date, no
    page was generated, and the live site served a homepage soft-404 while
    sitemap.xml still listed the URL (2 recipes lost, 2026-10-11).
    """
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\n", " ").replace("\r", " ").strip()
    return f'"{s}"'


def render_recipe_markdown(recipe: dict, slug: str) -> str:
    """Convert validated recipe JSON to Jekyll _recipes/<date>-<slug>.md."""
    today = datetime.now().strftime("%Y-%m-%d")
    n = recipe["nutrition_per_serving"]
    ingredients_api_yaml = "\n".join(f'  - "{ing}"' for ing in recipe["ingredients_api_format"])
    ingredients_display_yaml = "\n".join(f'  - "{ing}"' for ing in recipe["ingredients_display"])
    instructions_yaml = "\n".join(f'  - "{step.replace(chr(10), " ").strip()}"' for step in recipe["instructions"])
    diet_tags = recipe.get("diet_tags", ["Low-Calorie"])
    diet_tags_yaml = "[" + ", ".join(diet_tags) + "]"
    # Tags: cuisine + main ingredient + diet
    tags = [recipe["cuisine"].lower(), recipe["category"].lower()] + [t.lower() for t in diet_tags]
    tags_yaml = "[" + ", ".join(tags) + "]"

    return f"""---
title: {yaml_quote(recipe["recipe_name"])}
subtitle: {yaml_quote(recipe.get("meta_description", "")[:100])}
description: {yaml_quote(recipe["meta_description"])}
date: {today}
category: {recipe["category"]}
cuisine: {recipe["cuisine"]}
diet_tags: {diet_tags_yaml}
tags: {tags_yaml}
hero_image: /assets/recipes/{slug}.jpg
prep_time: {recipe["prep_time_mins"]}
cook_time: {recipe["cook_time_mins"]}
total_time: {recipe["total_time_mins"]}
servings: {recipe["servings"]}
calories: {n["calories"]}
protein: {n["protein_g"]}
carbs: {n["carbs_g"]}
fat: {n["fat_g"]}
fiber: {n["fiber_g"]}
ingredients_api:
{ingredients_api_yaml}
ingredients_display:
{ingredients_display_yaml}
instructions:
{instructions_yaml}
introduction: |
  {recipe["introduction"].strip()}
chef_tips: |
  {recipe["chef_tips"].strip()}
image_prompt: {recipe.get("image_prompt", "")}
---

# {recipe["recipe_name"]}

{recipe["introduction"].strip()}

## Ingredients

(Makes {recipe["servings"]} servings)

{chr(10).join(f"- {ing}" for ing in recipe["ingredients_display"])}

## Method

{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(recipe["instructions"]))}

## Nutrition (per serving)

- Calories: {n["calories"]} kcal
- Protein: {n["protein_g"]} g
- Carbohydrates: {n["carbs_g"]} g
- Fat: {n["fat_g"]} g
- Fiber: {n["fiber_g"]} g

## 👨‍🍳 Chef Tips

{recipe["chef_tips"].strip()}

---

*Developed in-house by our editorial kitchen, drawing on Mediterranean and Western culinary traditions. See our [Editorial Policy](/editorial-policy/) for our full standards.*
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate a healthy recipe")
    parser.add_argument("--count", type=int, default=1, help="Number of recipes to generate")
    parser.add_argument("--dry-run", action="store_true", help="Print but don't write")
    parser.add_argument("--theme", action="append", default=[], help="Override theme (repeatable; must supply --count == number of --theme args)")
    args = parser.parse_args()

    print(f"=== Healthy Recipe Pipeline ===")
    print(f"Date: {datetime.now().isoformat()}")
    print(f"Count: {args.count}, Dry-run: {args.dry_run}")

    recent_slugs = load_recent_slugs()
    recent_titles = load_recent_titles()
    print(f"Recent slugs (last {MAX_DAYS_BACK}d): {len(recent_slugs)}")
    print(f"Recent titles (last {MAX_DAYS_BACK}d): {len(recent_titles)}")

    RECIPES_DIR.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0

    for i in range(args.count):
        if args.theme and len(args.theme) == args.count:
            theme = args.theme[i]
        elif args.theme:
            print(f"  ⚠ --theme count ({len(args.theme)}) != --count ({args.count}); falling back to pick_theme()", file=sys.stderr)
            theme = pick_theme(recent_titles)
        else:
            theme = pick_theme(recent_titles)
        print(f"\n[{i+1}/{args.count}] Theme: {theme}")

        recipe = call_llm(theme)
        if recipe is None:
            print(f"  ⚠ LLM failed, skipping (no fallback mode in v1)", file=sys.stderr)
            skipped += 1
            continue

        slug = slugify(recipe["recipe_name"])
        if slug in recent_slugs:
            print(f"  ⚠ Duplicate slug '{slug}' — skipping")
            skipped += 1
            continue

        md = render_recipe_markdown(recipe, slug)
        today = datetime.now().strftime("%Y-%m-%d")
        out_path = RECIPES_DIR / f"{today}-{slug}.md"

        if args.dry_run:
            print(f"  DRY-RUN would write: {out_path}")
            print(f"  ({len(md)} chars)")
        else:
            # P45 inline atomic image gen — MUST run BEFORE write_text.
            # If this raises, .md is NOT written → cron abort → no broken
            # frontmatter enters working tree. Image + markdown must land
            # in the SAME commit.
            try:
                generate_hero_image(slug, recipe.get("image_prompt", ""))
            except Exception as e:
                print(f"  ❌ Hero image gen FAILED: {e}", file=sys.stderr)
                raise  # propagate up; cron wrapper will see non-zero exit

            out_path.write_text(md, encoding="utf-8")
            print(f"  ✓ Wrote: {out_path}")
            generated += 1
            recent_slugs.add(slug)
            recent_titles.append(recipe["recipe_name"])

    print(f"\n=== Summary ===")
    print(f"Generated: {generated}")
    print(f"Skipped:   {skipped}")
    print(f"Total recipes: {len(list(RECIPES_DIR.glob('*.md')))}")


if __name__ == "__main__":
    main()