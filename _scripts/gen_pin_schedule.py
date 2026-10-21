#!/usr/bin/env python3
"""W97 (2026-10-21): generate a Pinterest pin schedule for all recipes.

Produces two artefacts:
  _scripts/pinterest-schedule.csv   — bulk-importable (Tailwind, Pinterest scheduler)
  _scripts/pinterest-pin-pack.md    — human-readable preview

Why 5 variants per recipe: Pinterest treats identical images as duplicates and
limits their reach. Rotating hero / plate / hands / ingredients / recipe-card
images across weeks keeps every pin "fresh" (Pinterest ranks fresh images
higher), and 5x the pins = 5x the surface area for the same recipe.

Pin images are published at https://waimind.com/assets/pins/<slug>-<variant>.jpg
(832x1248, 2:3 — Pinterest's optimal ratio).

Schedule: 5 pins/day by default (≈77 days for 385 pins).
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "_recipes"
PINS = ROOT / "assets" / "pins"
SITE = "https://waimind.com"
CSV_OUT = Path(__file__).resolve().parent / "pinterest-schedule.csv"
MD_OUT = Path(__file__).resolve().parent / "pinterest-pin-pack.md"

VARIANTS = ["hero", "plate", "hands", "ingredients", "recipe-card"]
PINS_PER_DAY = 5
SLOTS = ["08:30", "11:00", "13:30", "17:00", "20:30"]

# Board routing: first matching tag wins
BOARD_RULES = [
    (("quick",), "Quick Healthy Dinners"),
    (("high-protein",), "High Protein Meals"),
    (("vegetarian", "vegan"), "Vegetarian Mediterranean"),
    (("soup",), "Healthy Soup Recipes"),
    (("salad",), "Healthy Salad Recipes"),
    (("side",), "Healthy Side Dishes"),
    (("breakfast",), "Healthy Breakfast Ideas"),
    (("greek",), "Greek Recipes"),
    (("italian",), "Italian Healthy Recipes"),
    (("spanish",), "Spanish Recipes"),
    (("moroccan", "turkish"), "Mediterranean Diet Recipes"),
]
DEFAULT_BOARD = "Low Calorie Recipes"


def parse(md: Path) -> dict:
    text = md.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    fm: dict = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" ") and not line.startswith("-"):
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"').strip("'")
    fn = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.+)\.md$", md.name)
    if fn:
        y, mo, d, slug = fn.groups()
        fm["_slug"] = slug
        fm["_url"] = f"{SITE}/{y}/{mo}/{d}/{slug}/"
        fm["_date"] = f"{y}-{mo}-{d}"
    return fm


def board_for(fm: dict) -> str:
    hay = " ".join([
        str(fm.get("tags", "")), str(fm.get("diet_tags", "")),
        str(fm.get("category", "")), str(fm.get("cuisine", "")),
    ]).lower()
    for keys, board in BOARD_RULES:
        if any(k in hay for k in keys):
            return board
    return DEFAULT_BOARD


def description(fm: dict) -> str:
    """First 40 chars carry the most Pinterest search weight."""
    title = fm.get("title", "Healthy recipe")
    cal = fm.get("calories", "")
    pro = fm.get("protein", "")
    mins = fm.get("total_time", "")
    bits = []
    if cal:
        bits.append(f"{cal} kcal")
    if pro:
        bits.append(f"{pro}g protein")
    if mins:
        bits.append(f"{mins} min")
    stat = f" ({', '.join(bits)})" if bits else ""
    desc = (
        f"{title}{stat} — a low-calorie Mediterranean recipe that's easy to make "
        f"on a weeknight. High protein, 400-600 kcal per serving. "
        f"#lowcalorie #highprotein #mediterraneandiet #healthyrecipes #easydinner"
    )
    return desc[:480]


rows = []
recipes = [parse(f) for f in sorted(RECIPES.glob("*.md"))]
recipes = [r for r in recipes if r.get("_slug")]

for r in recipes:
    for v in VARIANTS:
        img = PINS / f"{r['_slug']}-{v}.jpg"
        if not img.exists():
            continue
        rows.append({
            "slug": r["_slug"],
            "variant": v,
            "image_path": str(img),
            "title": (r.get("title", "") or "")[:95],
            "description": description(r),
            "link": r["_url"],
            "board": board_for(r),
        })

# Rotate so consecutive pins aren't the same recipe
rows.sort(key=lambda x: (x["variant"] != "hero", x["slug"], x["variant"]))

start = dt.date.today() + dt.timedelta(days=1)
for i, row in enumerate(rows):
    day = start + dt.timedelta(days=i // PINS_PER_DAY)
    row["date"] = day.isoformat()
    row["time"] = SLOTS[i % PINS_PER_DAY]
    row["image_url"] = f"{SITE}/assets/pins/{row['slug']}-{row['variant']}.jpg"

with CSV_OUT.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=[
        "date", "time", "board", "image_url", "title", "description", "link", "variant"])
    w.writeheader()
    for row in rows:
        w.writerow({k: row[k] for k in w.fieldnames})

md = [
    "# Waimind Pinterest Pin Pack",
    "",
    f"Auto-generated: {dt.datetime.now():%Y-%m-%d %H:%M} HKT",
    f"Total pins: **{len(rows)}** across **{len(recipes)} recipes** "
    f"({len(VARIANTS)} variants each)",
    f"Schedule: {PINS_PER_DAY} pins/day from {start} "
    f"→ ends {(start + dt.timedelta(days=(len(rows) - 1) // PINS_PER_DAY))}",
    "",
    "## How to use",
    "",
    "1. **Tailwind** (recommended): import `pinterest-schedule.csv`, map columns",
    "   `date/time → schedule`, `image_url → image`, `description → caption`, `link → destination`.",
    "2. **Pinterest native scheduler**: upload pins manually using the same date/time slots.",
    "3. Pin images are live at `https://waimind.com/assets/pins/<slug>-<variant>.jpg` (832x1248, 2:3).",
    "",
    "## Boards used",
    "",
]
board_counts: dict[str, int] = {}
for row in rows:
    board_counts[row["board"]] = board_counts.get(row["board"], 0) + 1
for b, c in sorted(board_counts.items(), key=lambda kv: -kv[1]):
    md.append(f"- {b}: {c} pins")

md += ["", "## First 20 pins", ""]
for row in rows[:20]:
    md.append(f"- **{row['date']} {row['time']}** · {row['board']}")
    md.append(f"  - {row['title']}")
    md.append(f"  - img: {row['image_url']}")
    md.append(f"  - link: {row['link']}")

MD_OUT.write_text("\n".join(md), encoding="utf-8")
print(f"✅ {CSV_OUT} ({len(rows)} rows)")
print(f"✅ {MD_OUT}")
print(f"   {len(recipes)} recipes × {len(VARIANTS)} variants, {PINS_PER_DAY}/day from {start}")
