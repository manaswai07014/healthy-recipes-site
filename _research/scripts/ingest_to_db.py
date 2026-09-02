#!/usr/bin/env python3
"""
ingest_to_db.py — Ingest adapted recipes into SQLite + export markdown.

Usage:
    python3 ingest_to_db.py [--dry-run]

Output:
    _research/data/recipes.db (SQLite WAL)
    _research/wiki/bbc/{date}-{slug}.md
    _research/wiki/eatingwell/{date}-{slug}.md
    Append entry to _research/wiki/log.md
"""
from __future__ import annotations
import argparse, json, os, sqlite3, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTED = ROOT / "adapted"
DATA = ROOT / "data"
WIKI = ROOT / "wiki"
DB_PATH = DATA / "recipes.db"
TODAY = datetime.now().strftime("%Y-%m-%d")

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    adapted_at TEXT NOT NULL,
    llm_model TEXT,
    validation_passed INTEGER NOT NULL,
    validation_errors TEXT,
    title TEXT NOT NULL,
    subtitle TEXT,
    description TEXT,
    cuisine TEXT,
    category TEXT,
    diet_tags TEXT,
    prep_time_min INTEGER,
    cook_time_min INTEGER,
    total_time_min INTEGER,
    servings INTEGER,
    calories INTEGER,
    protein_g INTEGER,
    carbs_g INTEGER,
    fat_g INTEGER,
    fiber_g INTEGER,
    ingredients_api TEXT,
    ingredients_display TEXT,
    instructions TEXT,
    introduction TEXT,
    chef_tips TEXT,
    image_prompt TEXT,
    jekyll_filename TEXT,
    published_to_site INTEGER DEFAULT 0,
    slug TEXT UNIQUE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source ON recipes(source);
CREATE INDEX IF NOT EXISTS idx_adapted_at ON recipes(adapted_at);
CREATE INDEX IF NOT EXISTS idx_validation ON recipes(validation_passed);
CREATE INDEX IF NOT EXISTS idx_published ON recipes(published_to_site);
"""

MD_TEMPLATE = """---
title: {title}
subtitle: {subtitle}
description: {description}
date: {today}
category: {category}
cuisine: {cuisine}
diet_tags: [{diet_tags}]
tags: [{tags}]
hero_image: /assets/recipes/{hero_slug}.jpg
prep_time: {prep}
cook_time: {cook}
total_time: {total}
servings: {servings}
calories: {cal}
protein: {pro}
carbs: {carbs}
fat: {fat}
fiber: {fiber}
ingredients_api:
{ingredients_api}
ingredients_display:
{ingredients_display}
instructions:
{instructions}
introduction: |
  {introduction}
chef_tips: |
  {chef_tips}
image_prompt: "{image_prompt}"
---

Developed, tested, and nutrition-verified by our editorial kitchen.

<!-- Source inspiration: {source} {source_url} (transformed/adapted). Wiki ref: {wiki_path} -->
"""

def init_db() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DB_SCHEMA)
    return conn

def yaml_list(items: list[str], indent: str = "  ") -> str:
    return "\n".join(f"{indent}- {json.dumps(i, ensure_ascii=False)}" for i in items)

def slugify(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]

def export_markdown(adapted: dict, source: str, slug: str) -> Path:
    r = adapted["recipe"]
    source_dir = WIKI / source
    source_dir.mkdir(parents=True, exist_ok=True)
    md = MD_TEMPLATE.format(
        title=r["title"],
        subtitle=r.get("subtitle", ""),
        description=r.get("description", ""),
        today=TODAY,
        category=r.get("category", "Main"),
        cuisine=r.get("cuisine", "Mediterranean"),
        diet_tags=", ".join(r.get("diet_tags", [])),
        tags=", ".join(r.get("diet_tags", [])[:3]),
        hero_slug=slug,
        prep=r.get("prep_time_min", ""),
        cook=r.get("cook_time_min", ""),
        total=r.get("total_time_min", ""),
        servings=r.get("servings", 4),
        cal=r.get("nutrition_per_serving", {}).get("calories", ""),
        pro=r.get("nutrition_per_serving", {}).get("protein_g", ""),
        carbs=r.get("nutrition_per_serving", {}).get("carbs_g", ""),
        fat=r.get("nutrition_per_serving", {}).get("fat_g", ""),
        fiber=r.get("nutrition_per_serving", {}).get("fiber_g", ""),
        ingredients_api=yaml_list(r.get("ingredients_api_format", [])),
        ingredients_display=yaml_list(r.get("ingredients_display", [])),
        instructions=yaml_list(r.get("instructions", [])),
        introduction=r.get("introduction", ""),
        chef_tips=r.get("chef_tips", ""),
        image_prompt=r.get("image_prompt", ""),
        source=source.upper(),
        source_url=adapted["source_url"],
        wiki_path=f"_research/wiki/{source}/{TODAY}-{slug}.md",
    )
    out = source_dir / f"{TODAY}-{slug}.md"
    out.write_text(md, encoding="utf-8")
    return out

def insert_recipe(conn: sqlite3.Connection, adapted: dict, source: str, slug: str, jekyll_path: Path) -> int:
    r = adapted["recipe"]
    n = r.get("nutrition_per_serving", {})
    jekyll_filename = jekyll_path.name
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO recipes (
            source, source_url, fetched_at, adapted_at, llm_model,
            validation_passed, validation_errors,
            title, subtitle, description, cuisine, category, diet_tags,
            prep_time_min, cook_time_min, total_time_min, servings,
            calories, protein_g, carbs_g, fat_g, fiber_g,
            ingredients_api, ingredients_display, instructions,
            introduction, chef_tips, image_prompt,
            jekyll_filename, slug
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source, adapted["source_url"], adapted["fetched_at"], adapted["adapted_at"], adapted.get("llm_model"),
        1 if adapted["validation"]["passed"] else 0, json.dumps(adapted["validation"]["errors"]),
        r.get("title", ""), r.get("subtitle", ""), r.get("description", ""),
        r.get("cuisine", ""), r.get("category", ""), json.dumps(r.get("diet_tags", [])),
        r.get("prep_time_min"), r.get("cook_time_min"), r.get("total_time_min"), r.get("servings") or 4,
        n.get("calories"), n.get("protein_g"), n.get("carbs_g"), n.get("fat_g"), n.get("fiber_g"),
        json.dumps(r.get("ingredients_api_format", [])), json.dumps(r.get("ingredients_display", [])),
        json.dumps(r.get("instructions", [])), r.get("introduction", ""), r.get("chef_tips", ""),
        r.get("image_prompt", ""), jekyll_filename, slug,
    ))
    conn.commit()
    return cur.lastrowid

def append_log(adapted: dict, source: str, slug: str, db_id: int, jekyll_path: Path):
    r = adapted["recipe"]
    status = "✓" if adapted["validation"]["passed"] else "✗"
    n = r.get("nutrition_per_serving", {})
    entry = (
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] [INGEST] "
        f"{status} {source.upper()} {r.get('title','')[:50]} | "
        f"cal={n.get('calories')} protein={n.get('protein_g')}g | "
        f"db_id={db_id} jekyll={jekyll_path.name} | "
        f"src={adapted['source_url']}\n"
    )
    log_path = WIKI / "log.md"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    adapted_files = sorted(ADAPTED.glob(f"{TODAY}-*.json"))
    if not adapted_files:
        print(f"[WARN] No adapted files for {TODAY}. Run adapt_recipes.py first.", file=sys.stderr)
        return 1

    print(f"=== Ingesting {len(adapted_files)} adapted recipes ===")
    conn = init_db()
    ingested = 0
    for path in adapted_files:
        adapted = json.loads(path.read_text(encoding="utf-8"))
        r = adapted["recipe"]
        source = adapted["source"]
        slug = slugify(r.get("title", "untitled"))
        jekyll_filename = f"{TODAY}-{slug}.md"

        # Write markdown
        md_path = export_markdown(adapted, source, slug)

        # Insert DB
        if args.dry_run:
            print(f"  [DRY] would ingest: {path.name} → {md_path}")
        else:
            db_id = insert_recipe(conn, adapted, source, slug, md_path)
            append_log(adapted, source, slug, db_id, md_path)
            status = "✓" if adapted["validation"]["passed"] else "✗"
            print(f"  {status} {md_path.name} (db_id={db_id})")
            ingested += 1

    print(f"\n=== TOTAL: {ingested} recipes ingested ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
