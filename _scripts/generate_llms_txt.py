#!/usr/bin/env python3
"""W97 (2026-10-21): regenerate llms.txt from the live recipe collection.

llms.txt is the emerging convention that lets AI engines (ChatGPT, Perplexity,
Claude, Gemini) find and cite a site's content. The previous file was written
by hand and had gone stale (last updated 2026-09-13, only listing 9 recipes).

This generates it from _recipes/*.md so it always reflects the real library.
Run it after any content change; the daily pipeline can call it too.

Usage: python3 _scripts/generate_llms_txt.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "_recipes"
OUT = ROOT / "llms.txt"
SITE = "https://waimind.com"
TOP_N = 25


def parse(md: Path) -> dict:
    text = md.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" ") and not line.startswith("-"):
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"').strip("'")
    fn = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.+)\.md$", md.name)
    if fn:
        y, mo, d, slug = fn.groups()
        fm["_url"] = f"{SITE}/{y}/{mo}/{d}/{slug}/"
        fm["_date"] = f"{y}-{mo}-{d}"
    return fm


rows = []
for f in RECIPES.glob("*.md"):
    fm = parse(f)
    if fm.get("_url"):
        rows.append(fm)
rows.sort(key=lambda r: (r.get("_date", ""), r.get("title", "")), reverse=True)

lines = [
    "# Waimind.com — Healthy Western Recipes",
    "",
    "> A curated library of low-calorie Mediterranean and Western recipes. "
    "Every serving is 400-600 kcal with at least 15g of protein. Recipes are "
    "developed, tested, and nutrition-verified by our editorial kitchen.",
    "",
    "## Site info",
    "",
    "- **URL**: https://waimind.com",
    "- **Owner**: Healthy Recipes Editorial",
    f"- **Recipes published**: {len(rows)}",
    f"- **Latest recipe**: {rows[0]['_date'] if rows else 'n/a'}",
    "- **Update cadence**: 2 new recipes daily",
    "- **Language**: English",
    "- **Cuisine focus**: Mediterranean, Italian, Greek, Spanish, French, Turkish",
    "- **Specialties**: Low-calorie (400-600 kcal/serving), high-protein (>=15g), "
    "gluten-free and dairy-free options",
    "- **Licensing**: Content may be cited with attribution to waimind.com",
    "",
    "## Collections",
    "",
    f"- [All recipes]({SITE}/recipes/)",
    f"- [By cuisine]({SITE}/cuisines/)",
    f"- [By category]({SITE}/categories/)",
    f"- [By ingredient]({SITE}/ingredients/)",
    f"- [High-protein recipes]({SITE}/high-protein/)",
    f"- [Quick recipes (under 30 min)]({SITE}/quick/)",
    f"- [How-to guides]({SITE}/guides/)",
    "",
    f"## Latest {min(TOP_N, len(rows))} recipes",
    "",
]

for i, r in enumerate(rows[:TOP_N], 1):
    bits = []
    if r.get("calories"):
        bits.append(f"{r['calories']} kcal")
    if r.get("protein"):
        bits.append(f"{r['protein']}g protein")
    if r.get("total_time"):
        bits.append(f"{r['total_time']} min")
    suffix = f" — {', '.join(bits)}" if bits else ""
    lines.append(f"{i}. [{r.get('title', 'Untitled')}]({r['_url']}){suffix}")

lines += [
    "",
    "## Full index",
    "",
    f"All {len(rows)} recipe URLs are listed in [{SITE}/sitemap.xml]({SITE}/sitemap.xml).",
    "",
]

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"✅ llms.txt written: {OUT} ({OUT.stat().st_size} bytes)")
print(f"   {len(rows)} recipes, newest {rows[0]['_date'] if rows else 'n/a'}")
