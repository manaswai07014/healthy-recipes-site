#!/usr/bin/env python3
"""
fetch_recipes.py — Scrape recipes from BBC Good Food + EatingWell.

Per 老闆's direction (2026-09-02), this is the FIRST step of the daily
research pipeline. Output: raw JSON per recipe in _research/raw/{source}/

Usage:
    python3 fetch_recipes.py [--count N] [--source bbc|eatingwell|both]

Output:
    _research/raw/bbc/{date}-{slug}.json
    _research/raw/eatingwell/{date}-{slug}.json

Each JSON contains:
    source: "bbc" | "eatingwell"
    source_url: full canonical URL
    source_title: original title
    fetch_timestamp: ISO 8601
    raw_html: full page HTML (audit trail)
    extracted: dict with metadata, ingredients, instructions, nutrition (best-effort)
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
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
]
EATINGWELL_SEEDS = [
    "https://www.eatingwell.com/recipes/18011/cuisines-regions/european/low-calorie/mediterranean/",
    "https://www.eatingwell.com/low-calorie-high-protein-mediterranean-diet-dinner-recipes-11987105",
    "https://www.eatingwell.com/three-step-low-calorie-mediterranean-diet-dinners-11771941",
]

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

def fetch(url: str, timeout: int = 30) -> str:
    """Fetch URL with browser-like headers."""
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")

def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:80] or "untitled"

def extract_recipe_from_html(html: str, source: str, url: str) -> dict:
    """Best-effort recipe extraction. Returns dict with metadata + content slices.

    Strategy: regex-based extraction of common patterns. NOT a full HTML parser —
    sufficient for audit trail + LLM adaptation input.
    """
    # Strip script/style tags
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)

    # Extract title (h1)
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else "Untitled"

    # Extract description (often in meta or first paragraph)
    desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html, re.IGNORECASE)
    description = desc_match.group(1).strip() if desc_match else ""

    # Extract ingredient-like list items
    ingredients = re.findall(r"<li[^>]*>(.*?)</li>", html, re.DOTALL | re.IGNORECASE)
    ingredients = [re.sub(r"<[^>]+>", "", i).strip() for i in ingredients if 10 < len(i) < 300]
    ingredients = [i for i in ingredients if re.search(r"\d", i) or re.search(r"(tsp|tbsp|cup|oz|g|kg|ml|l)\b", i, re.I)]

    # Extract step-like ordered list items (heuristic)
    steps = re.findall(r"<ol[^>]*>(.*?)</ol>", html, re.DOTALL | re.IGNORECASE)
    step_list = []
    for ol in steps:
        items = re.findall(r"<li[^>]*>(.*?)</li>", ol, re.DOTALL | re.IGNORECASE)
        for item in items:
            text = re.sub(r"<[^>]+>", "", item).strip()
            if 20 < len(text) < 1000:
                step_list.append(text)

    # Extract nutrition (look for kcal pattern)
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

    # Extract servings
    servings_match = re.search(r"serves?\s*(\d{1,3})", html, re.IGNORECASE)
    if servings_match:
        times["servings"] = int(servings_match.group(1))

    return {
        "source": source,
        "source_url": url,
        "source_title": title,
        "fetch_timestamp": datetime.now().isoformat(),
        "raw_html_size_bytes": len(html),
        "raw_html_excerpt": html[:3000],  # First 3KB for audit (NOT full content)
        "extracted": {
            "title": title,
            "description": description,
            "ingredients": ingredients[:30],  # Cap at 30 items
            "instructions": step_list[:20],  # Cap at 20 steps
            "nutrition": nutrition,
            "times": times,
            "ingredient_count": len(ingredients),
            "step_count": len(step_list),
        },
    }

def fetch_one(url: str, source: str) -> dict | None:
    try:
        html = fetch(url)
        return extract_recipe_from_html(html, source, url)
    except (HTTPError, URLError) as e:
        print(f"  [WARN] {source} {url}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [ERROR] {source} {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return None

def main():
    p = argparse.ArgumentParser(description="Fetch recipes from BBC Good Food + EatingWell")
    p.add_argument("--count", type=int, default=5, help="Recipes per source (default 5)")
    p.add_argument("--source", choices=["bbc", "eatingwell", "both"], default="both")
    args = p.parse_args()

    sources = []
    if args.source in ("bbc", "both"):
        sources.append(("bbc", BBC_SEEDS[:args.count]))
    if args.source in ("eatingwell", "both"):
        sources.append(("eatingwell", EATINGWELL_SEEDS[:args.count]))

    total = 0
    for source, urls in sources:
        out_dir = RAW / source
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"=== {source.upper()}: {len(urls)} URLs ===")
        for url in urls:
            data = fetch_one(url, source)
            if data is None:
                continue
            slug = slugify(data["extracted"]["title"])
            path = out_dir / f"{TODAY}-{slug}.json"
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"  ✓ {path.name}  ({data['extracted'].get('ingredient_count', 0)} ing, {data['extracted'].get('step_count', 0)} steps)")
            total += 1
            time.sleep(2)  # polite rate limit

    print(f"\n=== TOTAL: {total} recipes fetched ===")
    return 0 if total > 0 else 1

if __name__ == "__main__":
    sys.exit(main())
