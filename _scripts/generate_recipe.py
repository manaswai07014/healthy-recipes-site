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
LLM_MODEL = os.environ.get("RECIPE_LLM_MODEL", "MiniMax-M2")

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
  "seo_title": "Recipe name (under 30 characters, include one keyword)",
  "meta_description": "Description with core keyword (80-120 chars)",
  "recipe_name": "Full recipe name",
  "cuisine": "Italian | Mediterranean | French | Spanish | Greek | European | American",
  "category": "Main | Soup | Salad | Side",
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
    "Spanish albondigas (turkey meatballs) in tomato sauce",
    "Greek gemista (stuffed tomatoes and peppers)",
    "Italian pesto-crusted cod with green beans",
    "French soupe au pistou",
    "Spanish pulpo a la gallega (Galician octopus)",
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
def call_llm(theme: str, max_retries: int = 2) -> Optional[dict]:
    """Call MiniMax-M2 to generate recipe JSON. Returns dict or None on failure."""
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
def generate_hero_image(slug: str, image_prompt: str) -> Path:
    """Generate hero image and save to assets/recipes/{slug}.jpg.

    Returns the saved Path. Raises on any failure (no silent fallback).
    """
    if not LLM_API_KEY:
        raise RuntimeError(
            "MINIMAX_CN_API_KEY not set; cannot generate hero image. "
            "Source /home/hermes/.hermes/.env in cron wrapper."
        )
    if not image_prompt or len(image_prompt.strip()) < 10:
        raise ValueError(f"image_prompt too short/empty: {image_prompt!r}")

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
        raise RuntimeError(f"MiniMax image gen non-zero status: {body}")

    image_urls = body.get("data", {}).get("image_urls") or []
    if not image_urls:
        raise RuntimeError(f"MiniMax image gen returned no URLs: {body}")

    image_url = image_urls[0]
    out_path = ASSETS_DIR / f"{slug}.jpg"

    with urllib.request.urlopen(image_url, timeout=60) as img_resp:
        out_path.write_bytes(img_resp.read())

    # Sanity: file must be > 50KB and look like JPEG (JFIF magic bytes)
    if out_path.stat().st_size < 50_000:
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"hero image too small ({out_path.stat().st_size} bytes), discarded")
    with open(out_path, "rb") as f:
        magic = f.read(3)
    if magic != b"\xff\xd8\xff":
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"hero image not JPEG (magic={magic!r}), discarded")

    print(f"  🖼  Hero image: {out_path} ({out_path.stat().st_size} bytes)")
    return out_path


# ---------------------------------------------------------------------------
# Recipe → Markdown
# ---------------------------------------------------------------------------
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
title: {recipe["recipe_name"]}
subtitle: {recipe.get("meta_description", "")[:100]}
description: {recipe["meta_description"]}
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