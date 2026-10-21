#!/usr/bin/env python3
"""
fetch_recipes.py — Scrape recipes from public recipe sites.

Per 老闆's direction (2026-09-02 + extended 2026-09-03), this is the FIRST
step of the daily research pipeline. Output: raw JSON per recipe in
_research/raw/{source}/

Usage:
    python3 fetch_recipes.py [--count N] [--source SOURCE]
    python3 fetch_recipes.py --source both  # default

Supported sources:
    bbc              BBC Good Food (UK, public)
    acouplecooks     A Couple Cooks (US, vegetarian-friendly, JSON-LD)
    closecooking     Closet Cooking (Canada, fusion Mediterranean)
    budgetbytes      Budget Bytes (US, budget-friendly)
    eatingwell       EatingWell (US, returns 403 — kept for retries)
    both             bbc + acouplecooks (default — most diverse working sources)

Extraction strategy:
    1. JSON-LD @type=Recipe (preferred) — A Couple Cooks, Closet Cooking
    2. Microdata itemtype=Recipe (fallback) — Budget Bytes
    3. Regex-based (last resort) — BBC Good Food (no schema markup)

Output:
    _research/raw/{source}/{date}-{slug}.json
    Each JSON: source, source_url, source_title, fetch_timestamp, raw_html_size,
               extracted {title, description, ingredients, instructions, nutrition, times}
"""
from __future__ import annotations
import argparse, json, re, sys, time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
TODAY = datetime.now().strftime("%Y-%m-%d")

# ---------- Source recipe URL lists ----------
# Manually curated starting list. cron will expand via "related recipes" links.

BBC_SEEDS = [
    "https://www.bbcgoodfood.com/recipes/fish-soup",
    "https://www.bbcgoodfood.com/recipes/collection/healthy-mediterranean-recipes",
    "https://www.bbcgoodfood.com/health/mediterranean-diet-recipes",
    # W83 expansion: individual low-cal recipes with full nutrition data
    "https://www.bbcgoodfood.com/recipes/greek-style-roast-fish",
    "https://www.bbcgoodfood.com/recipes/turkey-meatballs",
    "https://www.bbcgoodfood.com/recipes/lentil-curry",
    "https://www.bbcgoodfood.com/recipes/chicken-shawarma",
    "https://www.bbcgoodfood.com/recipes/salmon-bowl",
    "https://www.bbcgoodfood.com/recipes/greek-yogurt-chicken",
    "https://www.bbcgoodfood.com/recipes/tuna-pasta",
    "https://www.bbcgoodfood.com/recipes/quinoa-salad",
    "https://www.bbcgoodfood.com/recipes/sweet-potato-curry",
    "https://www.bbcgoodfood.com/recipes/chicken-stir-fry",
    "https://www.bbcgoodfood.com/recipes/mediterranean-cod",
]
EATINGWELL_SEEDS = [
    "https://www.eatingwell.com/recipes/18011/cuisines-regions/european/low-calorie/mediterranean/",
    "https://www.eatingwell.com/low-calorie-high-protein-mediterranean-diet-dinner-recipes-11987105",
    "https://www.eatingwell.com/three-step-low-calorie-mediterranean-diet-dinners-11771941",
    # W83 expansion: more direct recipe URLs (gallery pages return 403)
    "https://www.eatingwell.com/recipe/248221/mediterranean-tuna-salad/",
    "https://www.eatingwell.com/recipe/248213/greek-chicken-bowls/",
    "https://www.eatingwell.com/recipe/248210/mediterranean-chicken-tray-bake/",
    "https://www.eatingwell.com/recipe/248205/lemon-herb-salmon/",
    "https://www.eatingwell.com/recipe/248200/tuna-white-bean-salad/",
]
A_COUPLE_COOKS_SEEDS = [
    "https://www.acouplecooks.com/burrata-pasta/",
    "https://www.acouplecooks.com/chickpea-couscous-bowls-tahini-sauce/",
    "https://www.acouplecooks.com/easy-mussels-marinara/",
    "https://www.acouplecooks.com/eggplant-caponata/",
    "https://www.acouplecooks.com/falafel-burger/",
    "https://www.acouplecooks.com/falafel-salad/",
    "https://www.acouplecooks.com/gazpacho-recipe/",
    "https://www.acouplecooks.com/greek-orzo-salad/",
    "https://www.acouplecooks.com/baked-shrimp-tomatoes-feta/",
    "https://www.acouplecooks.com/baked-tilapia/",
    # W83 expansion: more diverse (avoid repeating burrata + chickpea-couscous too often)
    "https://www.acouplecooks.com/greek-chicken-bowls/",
    "https://www.acouplecooks.com/mediterranean-chicken/",
    "https://www.acouplecooks.com/greek-pasta-salad/",
    "https://www.acouplecooks.com/gazpacho-soup/",
    "https://www.acouplecooks.com/roasted-vegetable-pasta/",
    "https://www.acouplecooks.com/lemon-chicken-orzo/",
    "https://www.acouplecooks.com/greek-yogurt-chicken/",
    "https://www.acouplecooks.com/salmon-bowl/",
    "https://www.acouplecooks.com/greek-chicken-gyros/",
    "https://www.acouplecooks.com/mediterranean-stuffed-peppers/",
]

# Low-calorie filter (skill P22: 400-600 kcal + ≥15g protein)
# Applied during fetch as pre-flight check. Recipes that fail are
# dropped from raw output (not ingested, not adapted).
MIN_CALORIES = 400
MAX_CALORIES = 600
MIN_PROTEIN_G = 15
CLOSET_COOKING_SEEDS = [
    "https://www.closetcooking.com/mediterranean-chicken/",
    "https://www.closetcooking.com/greek-chicken/",
    "https://www.closetcooking.com/italian-chicken/",
    "https://www.closetcooking.com/mediterranean-tuna-salad/",
    "https://www.closetcooking.com/greek-pasta-salad/",
]
BUDGET_BYTES_SEEDS = [
    "https://www.budgetbytes.com/greek-chicken-bowls/",
    "https://www.budgetbytes.com/mediterranean-chicken/",
    "https://www.budgetbytes.com/greek-pasta-salad/",
    "https://www.budgetbytes.com/hummus-bowl/",
    "https://www.budgetbytes.com/mediterranean-tuna-salad/",
]

# (key, label, url list) — used by --source argument
SOURCES = {
    "bbc": ("BBC Good Food", BBC_SEEDS),
    "eatingwell": ("EatingWell", EATINGWELL_SEEDS),
    "acouplecooks": ("A Couple Cooks", A_COUPLE_COOKS_SEEDS),
    "closetcooking": ("Closet Cooking", CLOSET_COOKING_SEEDS),
    "budgetbytes": ("Budget Bytes", BUDGET_BYTES_SEEDS),
}
DEFAULT_SOURCES = ["bbc", "acouplecooks"]  # 'both' default = 2 diverse, working sources

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

def fetch(url: str, timeout: int = 30) -> str:
    """Fetch URL with browser-like headers."""
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")

def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:80] or "untitled"

# ---------- Extraction strategies ----------

def strip_html(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def parse_iso_duration(duration: str) -> dict:
    """Parse ISO 8601 duration (PT15M, PT1H30M) → minutes."""
    if not duration:
        return {}
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration)
    if not match:
        return {}
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return {"total_minutes": hours * 60 + minutes}

def parse_recipe_jsonld(html: str) -> dict | None:
    """Extract recipe data from JSON-LD <script type='application/ld+json'>.
    Returns dict with title/ingredients/instructions/nutrition/times, or None if not present.
    """
    # Find all JSON-LD blocks
    pattern = r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

    for raw in matches:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # JSON-LD can be a single object, array, or @graph
        if isinstance(data, dict) and "@graph" in data:
            data = data["@graph"]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") in ("Recipe", ["Recipe"]):
                    return normalize_jsonld_recipe(item)
        elif isinstance(data, dict):
            if data.get("@type") in ("Recipe", ["Recipe"]):
                return normalize_jsonld_recipe(data)
    return None

def normalize_jsonld_recipe(data: dict) -> dict:
    """Convert JSON-LD Recipe object → internal extracted format."""
    def get_list(field):
        v = data.get(field, [])
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(item) if not isinstance(item, dict) else strip_html(str(item)) for item in v]
        return []

    ingredients = []
    for item in get_list("recipeIngredient"):
        s = strip_html(item) if "<" in str(item) else str(item)
        ingredients.append(s.strip())

    instructions = []
    for item in get_list("recipeInstructions"):
        if isinstance(item, dict) and "itemListElement" in item:
            for sub in item["itemListElement"]:
                if isinstance(sub, dict):
                    instructions.append(strip_html(sub.get("text", "")).strip())
                else:
                    instructions.append(strip_html(str(sub)).strip())
        elif isinstance(item, str):
            instructions.append(strip_html(item).strip())
        elif isinstance(item, dict):
            instructions.append(strip_html(item.get("text", "")).strip())

    nutrition = {}
    nut = data.get("nutrition", {})
    if isinstance(nut, dict):
        if "calories" in nut:
            cal_str = str(nut["calories"]).split()[0]
            try:
                nutrition["calories_kcal"] = int(cal_str)
            except (ValueError, IndexError):
                pass
        for k in ("proteinContent", "carbohydrateContent", "fatContent", "fiberContent"):
            if k in nut:
                val_str = str(nut[k]).split()[0]
                try:
                    nutrition[k.replace("Content", "_g").lower()] = float(val_str)
                except (ValueError, IndexError):
                    pass

    times = {}
    prep = data.get("prepTime", "")
    cook = data.get("cookTime", "")
    total = data.get("totalTime", "")
    for label, dur in [("prep_minutes", prep), ("cook_minutes", cook), ("total_minutes", total)]:
        parsed = parse_iso_duration(dur)
        if parsed:
            times[label] = parsed["total_minutes"]
    yield_val = data.get("recipeYield", "")
    if yield_val:
        m = re.search(r"(\d+)", str(yield_val))
        if m:
            times["servings"] = int(m.group(1))

    return {
        "title": strip_html(data.get("name", "")).strip(),
        "description": strip_html(data.get("description", "")).strip()[:500],
        "ingredients": ingredients[:30],
        "instructions": instructions[:20],
        "nutrition": nutrition,
        "times": times,
        "ingredient_count": len(ingredients),
        "step_count": len(instructions),
        "extraction_method": "json-ld",
    }

def extract_recipe_from_html(html: str, source: str, url: str) -> dict:
    """Best-effort recipe extraction. Tries JSON-LD first, falls back to regex.

    Strategy:
    1. JSON-LD @type=Recipe (preferred — A Couple Cooks, Closet Cooking)
    2. Regex-based extraction (BBC Good Food, fallback)
    """
    # Try JSON-LD first (works for acouplecooks, closecooking, budgetbytes)
    jsonld_result = parse_recipe_jsonld(html)
    if jsonld_result and jsonld_result["ingredient_count"] >= 3:
        extracted = jsonld_result
    else:
        # Fallback: regex (works for BBC, no schema markup)
        extracted = extract_via_regex(html)

    # Extract page title from <title> or <h1> as fallback
    if not extracted.get("title") or extracted["title"] == "Untitled":
        title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
        if title_match:
            extracted["title"] = strip_html(title_match.group(1)).strip()

    return {
        "source": source,
        "source_url": url,
        "source_title": extracted.get("title", "Untitled"),
        "fetch_timestamp": datetime.now().isoformat(),
        "raw_html_size_bytes": len(html),
        "raw_html_excerpt": html[:3000],
        "extracted": extracted,
    }

def extract_via_regex(html: str) -> dict:
    """Regex-based extraction. Used when JSON-LD is unavailable."""
    # Strip script/style tags
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)

    # Extract title (h1)
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    title = strip_html(title_match.group(1)).strip() if title_match else "Untitled"

    # Extract description
    desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html, re.IGNORECASE)
    description = desc_match.group(1).strip() if desc_match else ""

    # Extract ingredient-like list items
    ingredients = re.findall(r"<li[^>]*>(.*?)</li>", html, re.DOTALL | re.IGNORECASE)
    ingredients = [strip_html(i) for i in ingredients if 10 < len(i) < 300]
    ingredients = [i for i in ingredients if re.search(r"\d", i) or re.search(r"(tsp|tbsp|cup|oz|g|kg|ml|l)\b", i, re.I)]

    # Extract step-like ordered list items
    steps = re.findall(r"<ol[^>]*>(.*?)</ol>", html, re.DOTALL | re.IGNORECASE)
    step_list = []
    for ol in steps:
        items = re.findall(r"<li[^>]*>(.*?)</li>", ol, re.DOTALL | re.IGNORECASE)
        for item in items:
            text = strip_html(item)
            if 20 < len(text) < 1000:
                step_list.append(text)

    # Extract nutrition
    nutrition = {}
    kcal_match = re.search(r"(\d{2,4})\s*kcal", html, re.IGNORECASE)
    if kcal_match:
        nutrition["calories_kcal"] = int(kcal_match.group(1))
    protein_match = re.search(r"protein[^0-9]*(\d{1,3})\s*g", html, re.IGNORECASE)
    if protein_match:
        nutrition["protein_g"] = int(protein_match.group(1))

    # Extract prep/cook time
    times = {}
    for label, pattern in [("prep_minutes", r"prep[^0-9]*(\d{1,3})\s*min"), ("cook_minutes", r"cook[^0-9]*(\d{1,3})\s*min")]:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            times[label] = int(m.group(1))
    servings_match = re.search(r"serves?\s*(\d{1,3})", html, re.IGNORECASE)
    if servings_match:
        times["servings"] = int(servings_match.group(1))

    return {
        "title": title,
        "description": description,
        "ingredients": ingredients[:30],
        "instructions": step_list[:20],
        "nutrition": nutrition,
        "times": times,
        "ingredient_count": len(ingredients),
        "step_count": len(step_list),
        "extraction_method": "regex",
    }

def passes_nutrition_filter(extracted: dict) -> tuple[bool, str]:
    """Check if recipe meets healthy recipes nutrition criteria (P22).
    Returns (passes, reason). Reason is empty when passes=True.
    Rules: 400 ≤ calories ≤ 600 AND protein ≥ 15g (when nutrition is present).
    If nutrition data is missing, recipe is rejected (we don't LLM-fill calories).
    """
    nutrition = extracted.get("nutrition", {})
    cal = nutrition.get("calories_kcal")
    prot = nutrition.get("protein_g")
    if cal is None or prot is None:
        return False, "missing nutrition data (calories or protein)"
    if cal < MIN_CALORIES:
        return False, f"too low cal: {cal} kcal (<{MIN_CALORIES})"
    if cal > MAX_CALORIES:
        return False, f"too high cal: {cal} kcal (>{MAX_CALORIES})"
    if prot < MIN_PROTEIN_G:
        return False, f"too low protein: {prot}g (<{MIN_PROTEIN_G}g)"
    return True, ""

def fetch_one(url: str, source: str) -> dict | None:
    try:
        html = fetch(url)
        data = extract_recipe_from_html(html, source, url)
    except (HTTPError, URLError) as e:
        print(f"  [WARN] {source} {url}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [ERROR] {source} {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return None

    # Pre-flight nutrition filter (P22)
    extracted = data["extracted"]
    passes, reason = passes_nutrition_filter(extracted)
    if not passes:
        cal = extracted.get("nutrition", {}).get("calories_kcal", "MISSING")
        prot = extracted.get("nutrition", {}).get("protein_g", "MISSING")
        print(f"  [SKIP:nutrition] {data['extracted']['title'][:40]} | cal={cal} protein={prot}g | reason={reason}")
        return None
    return data

def main():
    p = argparse.ArgumentParser(description="Fetch recipes from public recipe sites")
    p.add_argument("--count", type=int, default=5, help="Recipes per source (default 5)")
    source_choices = list(SOURCES.keys()) + ["both"]
    p.add_argument("--source", choices=source_choices, default="both",
                   help="Which source(s) to fetch (default 'both' = bbc + acouplecooks)")
    args = p.parse_args()

    if args.source == "both":
        sources = [(k, *SOURCES[k]) for k in DEFAULT_SOURCES]
    else:
        label, urls = SOURCES[args.source]
        sources = [(args.source, label, urls)]

    total = 0
    for source_key, label, urls in sources:
        out_dir = RAW / source_key
        out_dir.mkdir(parents=True, exist_ok=True)
        urls_to_fetch = urls[:args.count]
        print(f"=== {label} ({source_key}): {len(urls_to_fetch)} URLs ===")
        for url in urls_to_fetch:
            data = fetch_one(url, source_key)
            if data is None:
                continue
            slug = slugify(data["extracted"]["title"])
            path = out_dir / f"{TODAY}-{slug}.json"
            # Skip if already exists (idempotent re-runs)
            if path.exists():
                print(f"  [SKIP] {path.name} already exists")
                continue
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            method = data["extracted"].get("extraction_method", "unknown")
            print(f"  ✓ {path.name}  ({data['extracted'].get('ingredient_count', 0)} ing, {data['extracted'].get('step_count', 0)} steps, method={method})")
            total += 1
            time.sleep(2)  # polite rate limit

    print(f"\n=== TOTAL: {total} recipes fetched ===")
    return 0 if total > 0 else 1

if __name__ == "__main__":
    sys.exit(main())