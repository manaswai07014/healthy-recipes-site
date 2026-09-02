#!/usr/bin/env python3
"""
adapt_recipes.py — LLM-adapt raw scraped recipes for our editorial style.

Per 老闆's direction (2026-09-02): transform BBC Good Food / EatingWell
recipes into our in-house editorial style with 400-600 kcal + ≥15g protein.

Transformation rules:
1. NEVER copy verbatim long passages — always paraphrase
2. Recompute nutrition to fit our 400-600 kcal / ≥15g protein target
3. Add chef_tips based on technique
4. Rewrite introduction + chef_tips in our editorial voice
5. Generate proper Jekyll _recipes/ frontmatter

Usage:
    python3 adapt_recipes.py [--count N] [--dry-run]

Output:
    _research/adapted/{date}-{slug}.json (transformed recipe)
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
ADAPTED = ROOT / "adapted"
TODAY = datetime.now().strftime("%Y-%m-%d")

# ---------- LLM config (Hermes MiniMax CN) ----------
LLM_ENDPOINT = os.environ.get("MINIMAX_CN_BASE_URL", "https://api.minimaxi.com/anthropic")
LLM_API_KEY = os.environ.get("MINIMAX_CN_API_KEY", "")
LLM_MODEL = os.environ.get("RECIPE_LLM_MODEL", "MiniMax-M2.7")

# ---------- Editorial standards ----------
MIN_CALORIES = 400
MAX_CALORIES = 600
MIN_PROTEIN = 15

ADAPT_SYSTEM_PROMPT = """You are the head chef and editorial director at Healthy Western Recipes, a low-calorie Mediterranean and Western cooking publication.

Your editorial standards:
- Every serving: 400-600 kcal, at least 15g protein
- Recipes must be developable with Western supermarket ingredients
- Technique is specific (times, temperatures, sensory cues)
- No clichés like "easy", "simple", "delicious" without backing them up

CRITICAL TRANSFORMATION RULES:
1. NEVER reproduce verbatim text from the source — always PARAPHRASE in your own voice
2. KEEP the core recipe concept (main protein, vegetables, cooking technique) so the dish is recognizable
3. ADJUST ingredients/quantities to meet 400-600 kcal AND ≥15g protein per serving
4. If the source recipe doesn't fit our standards, modify it (swap ingredient, reduce portion, add veg)
5. WRITE a fresh introduction (150-200 words) in our editorial voice
6. WRITE 1-2 paragraphs of chef_tips with technique variations and storage notes
7. The adapted recipe should feel LIKE OUR ORIGINAL CREATION, not a rewrite of someone else's

Output strictly as JSON with this exact schema:
{
  "title": "Recipe Title",
  "subtitle": "One-line description",
  "description": "80-120 char meta description",
  "cuisine": "Italian | Mediterranean | French | Spanish | Greek | European | American | Asian",
  "category": "Main | Soup | Salad | Side",
  "diet_tags": ["Low-Calorie", "High-Protein", "Quick"],
  "prep_time_min": 15,
  "cook_time_min": 25,
  "total_time_min": 40,
  "servings": 2,
  "nutrition_per_serving": {
    "calories": 450,
    "protein_g": 35,
    "carbs_g": 25,
    "fat_g": 18,
    "fiber_g": 6
  },
  "ingredients_api_format": ["<qty> <unit> <english name>", "..."],
  "ingredients_display": ["Friendly display name with qty", "..."],
  "instructions": ["Step 1: detailed step", "..."],
  "introduction": "150-200 word intro with sensory detail",
  "chef_tips": "1-2 paragraphs of technique variations",
  "image_prompt": "Overhead shot of <dish>, 16:9 food photography"
}"""

ADAPT_USER_TEMPLATE = """Adapt this source recipe into our in-house editorial style.

SOURCE TITLE: {title}
SOURCE URL: {url}
SOURCE DESCRIPTION: {description}
SOURCE INGREDIENTS (extracted):
{ingredients}

SOURCE STEPS (extracted):
{steps}

SOURCE NUTRITION (extracted): {nutrition}

CRITICAL REQUIREMENTS:
1. Recalculate nutrition to 400-600 kcal AND ≥15g protein per serving
2. If source nutrition doesn't meet target, modify the recipe (smaller portions, swap ingredients)
3. PARAPHRASE everything — no verbatim copy from source
4. Output strict JSON only, no markdown fences, no commentary"""

def call_llm(raw: dict, dry_run: bool = False) -> dict | None:
    """Call MiniMax-M2.7 to adapt a raw recipe."""
    if dry_run:
        # Mock adapted recipe for testing pipeline without API call
        return {
            "title": f"[DRY RUN] {raw['extracted']['title']}",
            "subtitle": "Dry-run adaptation",
            "description": "Mock description",
            "cuisine": "Mediterranean",
            "category": "Main",
            "diet_tags": ["Low-Calorie", "High-Protein"],
            "prep_time_min": 15,
            "cook_time_min": 20,
            "total_time_min": 35,
            "servings": 2,
            "nutrition_per_serving": {"calories": 450, "protein_g": 30, "carbs_g": 30, "fat_g": 15, "fiber_g": 6},
            "ingredients_api_format": ["2 tbsp olive oil", "..."],
            "ingredients_display": ["2 tbsp olive oil", "..."],
            "instructions": ["Step 1: ...", "..."],
            "introduction": "[DRY RUN] Adapted introduction.",
            "chef_tips": "[DRY RUN] Chef tips.",
            "image_prompt": "[DRY RUN] image prompt",
        }

    if not LLM_API_KEY:
        print("[ERROR] MINIMAX_CN_API_KEY not set", file=sys.stderr)
        return None

    user_prompt = ADAPT_USER_TEMPLATE.format(
        title=raw["extracted"]["title"],
        url=raw["source_url"],
        description=raw["extracted"]["description"],
        ingredients="\n".join(f"  - {i}" for i in raw["extracted"]["ingredients"]),
        steps="\n".join(f"  {n+1}. {s}" for n, s in enumerate(raw["extracted"]["instructions"])),
        nutrition=raw["extracted"]["nutrition"],
    )

    import urllib.request, json as jsonlib
    payload = {
        "model": LLM_MODEL,
        "max_tokens": 4096,
        "system": ADAPT_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    req = urllib.request.Request(
        LLM_ENDPOINT.rstrip("/") + "/v1/messages",
        data=jsonlib.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": LLM_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = jsonlib.loads(resp.read().decode("utf-8"))
        text = ""
        for block in body.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())
        return jsonlib.loads(text)
    except Exception as e:
        print(f"[ERROR] LLM call failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None

def validate(recipe: dict) -> tuple[bool, list[str]]:
    """Check recipe meets our editorial standards. Returns (ok, errors)."""
    errors = []
    n = recipe.get("nutrition_per_serving", {})
    cal = n.get("calories", 0)
    pro = n.get("protein_g", 0)
    if not (MIN_CALORIES <= cal <= MAX_CALORIES):
        errors.append(f"calories {cal} out of range [{MIN_CALORIES}, {MAX_CALORIES}]")
    if pro < MIN_PROTEIN:
        errors.append(f"protein {pro}g below minimum {MIN_PROTEIN}g")
    required = ["title", "subtitle", "description", "ingredients_display", "instructions", "introduction", "chef_tips"]
    for k in required:
        if not recipe.get(k):
            errors.append(f"missing required field: {k}")
    return (len(errors) == 0, errors)

def main():
    p = argparse.ArgumentParser(description="Adapt raw recipes via LLM")
    p.add_argument("--count", type=int, default=5, help="Max recipes to adapt today")
    p.add_argument("--dry-run", action="store_true", help="Skip LLM call, use mock")
    args = p.parse_args()

    # Find today's raw files
    raw_files = []
    for source_dir in (RAW / "bbc", RAW / "eatingwell"):
        if source_dir.exists():
            raw_files.extend(sorted(source_dir.glob(f"{TODAY}-*.json")))

    if not raw_files:
        print(f"[WARN] No raw files for {TODAY}. Run fetch_recipes.py first.", file=sys.stderr)
        return 1

    raw_files = raw_files[:args.count]
    print(f"=== Adapting {len(raw_files)} raw recipes ===")

    ADAPTED.mkdir(parents=True, exist_ok=True)
    adapted_count = 0
    rejected_count = 0

    for raw_path in raw_files:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        print(f"\n--- {raw['extracted']['title'][:60]} ---")

        adapted = call_llm(raw, dry_run=args.dry_run)
        if adapted is None:
            print(f"  [SKIP] LLM failed")
            rejected_count += 1
            continue

        ok, errors = validate(adapted)
        slug = re.sub(r"[^a-z0-9]+", "-", adapted.get("title", "untitled").lower()).strip("-")[:80]
        out = {
            "source": raw["source"],
            "source_url": raw["source_url"],
            "fetched_at": raw["fetch_timestamp"],
            "adapted_at": datetime.now().isoformat(),
            "llm_model": LLM_MODEL,
            "validation": {"passed": ok, "errors": errors},
            "recipe": adapted,
        }
        out_path = ADAPTED / f"{TODAY}-{slug}.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

        if ok:
            print(f"  ✓ {out_path.name}  (validated)")
            adapted_count += 1
        else:
            print(f"  ✗ {out_path.name}  REJECTED: {', '.join(errors)}")
            rejected_count += 1

    print(f"\n=== Summary: {adapted_count} adapted, {rejected_count} rejected ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
