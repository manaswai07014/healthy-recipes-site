#!/usr/bin/env python3
"""
publish_to_site.py — Publish validated research-wiki recipes to live Jekyll site.

Reads SQLite for recipes with published_to_site=0 AND validation_passed=1,
runs dedup check against existing _recipes/, renders Jekyll markdown to
_recipes/<date>-<slug>.md, generates hero image via MCP, commits, and pushes.

Dedup rule (P44 hard rule):
- Reject if jekyll_filename (date-prefixed) already exists in _recipes/
- Reject if title has ≥2 keyword overlap (≥4-char words) with any published recipe
- Mark rejected recipes with validation_errors note in SQLite (audit only)

Usage:
    python3 publish_to_site.py [--dry-run] [--limit N]

Cron context:
    This script runs AFTER fetch → adapt → ingest (cron 0 4 * * *)
    LLM key is loaded from /home/hermes/.hermes/.env (cron context has no shell env)

P26 invariant:
    Every published recipe MUST have a real hero image in assets/recipes/.
    Image is generated via MiniMax text-to_image MCP tool (called externally,
    not in this script). Caller must ensure image file exists before commit.

P28 invariant:
    Jekyll markdown hero_image path uses raw slug (no date prefix) to match
    the image filename.
"""
from __future__ import annotations
import argparse, json, os, re, sqlite3, subprocess, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # healthy-recipes-site/
RESEARCH = ROOT / "_research"
DB_PATH = RESEARCH / "data" / "recipes.db"
ADAPTED_DIR = RESEARCH / "adapted"
RECIPES_DIR = ROOT / "_recipes"
ASSETS_RECIPES = ROOT / "assets" / "recipes"
TODAY = datetime.now().strftime("%Y-%m-%d")

HERMES_PYTHON = "/home/hermes/apps/hermes-agent/venv/bin/python3"

def load_env():
    """Source Hermes .env so subprocesses inherit LLM keys (cron context)."""
    env_file = Path("/home/hermes/.hermes/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]

def keywords(title: str) -> set[str]:
    """Extract words ≥4 chars from title for fuzzy dedup."""
    return set(w.lower() for w in re.findall(r"[A-Za-z]{4,}", title))

def yaml_list(items: list[str], indent: str = "  ") -> str:
    return "\n".join(f"{indent}- \"{i}\"" for i in items)

def get_unpublished(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT id, source, source_url, title, subtitle, description,
               cuisine, category, diet_tags,
               prep_time_min, cook_time_min, total_time_min, servings,
               calories, protein_g, carbs_g, fat_g, fiber_g,
               ingredients_api, ingredients_display, instructions,
               introduction, chef_tips, image_prompt,
               jekyll_filename, slug
        FROM recipes
        WHERE published_to_site = 0 AND validation_passed = 1
        ORDER BY id
    """)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_published_titles() -> list[str]:
    """Read all current _recipes/*.md titles for fuzzy dedup."""
    titles = []
    if not RECIPES_DIR.exists():
        return []
    for md in RECIPES_DIR.glob("*.md"):
        try:
            for line in md.read_text(encoding="utf-8").splitlines():
                if line.startswith("title:"):
                    titles.append(line.split(":", 1)[1].strip())
                    break
        except Exception:
            continue
    return titles

def check_dedup(slug: str, title: str, published_titles: list[str]) -> tuple[bool, str]:
    """Return (ok, reason). ok=True means safe to publish."""
    # 1. Slug filename collision
    jekyll_filename = f"{TODAY}-{slug}.md"
    if (RECIPES_DIR / jekyll_filename).exists():
        return False, f"slug collision: {jekyll_filename} already exists"

    # 2. Keyword overlap with published titles (≥2 words)
    pk = keywords(title)
    for pt in published_titles:
        tk = keywords(pt)
        overlap = pk & tk
        if len(overlap) >= 2:
            return False, f"keyword overlap with published \"{pt}\": {overlap}"
    return True, "ok"

def render_markdown(r: dict, slug: str) -> str:
    """Render Jekyll recipe markdown. hero_image uses raw slug (P28 invariant)."""
    ingredients_api = json.loads(r["ingredients_api"]) if r["ingredients_api"] else []
    ingredients_display = json.loads(r["ingredients_display"]) if r["ingredients_display"] else []
    instructions = json.loads(r["instructions"]) if r["instructions"] else []
    diet_tags = json.loads(r["diet_tags"]) if r["diet_tags"] else []

    hero_slug = slug  # raw slug, no date prefix
    fm = {
        "title": r["title"],
        "subtitle": r["subtitle"] or "",
        "description": r["description"] or "",
        "date": TODAY,
        "category": r["category"] or "Main",
        "cuisine": r["cuisine"] or "Mediterranean",
        "diet_tags": diet_tags,
        "tags": diet_tags[:5],
        "hero_image": f"/assets/recipes/{hero_slug}.jpg",
        "prep_time": r["prep_time_min"] or 0,
        "cook_time": r["cook_time_min"] or 0,
        "total_time": r["total_time_min"] or 0,
        "servings": r["servings"] or 2,
        "calories": r["calories"] or 0,
        "protein": r["protein_g"] or 0,
        "carbs": r["carbs_g"] or 0,
        "fat": r["fat_g"] or 0,
        "fiber": r["fiber_g"] or 0,
        "ingredients_api": ingredients_api,
        "ingredients_display": ingredients_display,
        "instructions": instructions,
        "introduction": r["introduction"] or "",
        "chef_tips": r["chef_tips"] or "",
        "image_prompt": r["image_prompt"] or "",
    }
    # Manual YAML emit (preserve order, avoid yaml lib complexity)
    lines = ["---"]
    lines.append(f"title: {fm['title']}")
    lines.append(f"subtitle: {fm['subtitle']}")
    lines.append(f"description: {fm['description']}")
    lines.append(f"date: {fm['date']}")
    lines.append(f"category: {fm['category']}")
    lines.append(f"cuisine: {fm['cuisine']}")
    lines.append("diet_tags: [" + ", ".join(diet_tags) + "]")
    lines.append("tags: [" + ", ".join(diet_tags[:5]) + "]")
    lines.append(f"hero_image: {fm['hero_image']}")
    lines.append(f"prep_time: {fm['prep_time']}")
    lines.append(f"cook_time: {fm['cook_time']}")
    lines.append(f"total_time: {fm['total_time']}")
    lines.append(f"servings: {fm['servings']}")
    lines.append(f"calories: {fm['calories']}")
    lines.append(f"protein: {fm['protein']}")
    lines.append(f"carbs: {fm['carbs']}")
    lines.append(f"fat: {fm['fat']}")
    lines.append(f"fiber: {fm['fiber']}")
    lines.append("ingredients_api:")
    for ing in ingredients_api:
        lines.append(f'  - "{ing}"')
    lines.append("ingredients_display:")
    for ing in ingredients_display:
        lines.append(f'  - "{ing}"')
    lines.append("instructions:")
    for step in instructions:
        lines.append(f'  - "{step}"')
    lines.append("introduction: |")
    for line in (r["introduction"] or "").splitlines():
        lines.append(f"  {line}")
    lines.append("chef_tips: |")
    for line in (r["chef_tips"] or "").splitlines():
        lines.append(f"  {line}")
    if r["image_prompt"]:
        lines.append(f'image_prompt: "{r["image_prompt"]}"')
    lines.append("---")
    lines.append("")
    lines.append(f"# {fm['title']}")
    lines.append("")
    lines.append(r["introduction"] or "")
    lines.append("")
    lines.append("## Ingredients")
    lines.append("")
    for ing in ingredients_display:
        lines.append(f"- {ing}")
    lines.append("")
    lines.append("## Instructions")
    lines.append("")
    for i, step in enumerate(instructions, 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    lines.append("## Chef's Tips")
    lines.append("")
    lines.append(r["chef_tips"] or "")
    lines.append("")
    return "\n".join(lines)

def mark_published(conn: sqlite3.Connection, rid: int):
    conn.execute("UPDATE recipes SET published_to_site = 1 WHERE id = ?", (rid,))
    conn.commit()

def mark_rejected(conn: sqlite3.Connection, rid: int, reason: str):
    """Mark recipe as rejected in audit trail (won't publish)."""
    err = json.dumps([f"REJECTED auto-publish {TODAY}: {reason}"])
    conn.execute("""
        UPDATE recipes
        SET validation_passed = 0, validation_errors = ?
        WHERE id = ?
    """, (err, rid))
    conn.commit()

def git_commit_push(dry_run: bool) -> bool:
    """Stage _recipes/ + assets/recipes/ changes, commit, push."""
    if dry_run:
        print("  [DRY] would git add + commit + push")
        return True

    subprocess.run(["git", "add", "_recipes/"], cwd=ROOT, check=True)
    subprocess.run(["git", "add", "assets/recipes/"], cwd=ROOT, check=True)

    # Check if anything staged
    res = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=ROOT,
    )
    if res.returncode == 0:
        print("  [INFO] no staged changes (nothing to commit)")
        return False

    msg = f"feat(recipe): auto-publish research wiki recipes {TODAY}"
    subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True)
    res = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT,
                         capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  [ERROR] git push failed: {res.stderr}")
        return False
    print(f"  [OK] committed + pushed")
    return True

def generate_image(image_prompt: str, slug: str, dry_run: bool) -> Path | None:
    """Generate hero image via MiniMax direct API call.
    Uses scripts/generate_hero_image.py logic inline to avoid subprocess overhead.
    """
    image_path = ASSETS_RECIPES / f"{slug}.jpg"
    if image_path.exists():
        print(f"  [OK] image already exists: {image_path.name}")
        return image_path
    if dry_run:
        print(f"  [DRY] would generate image: {slug}.jpg from prompt: {image_prompt[:60]}...")
        return None

    # Inline call to MiniMax image gen API
    import urllib.request, urllib.error
    api_key = None
    env_file = Path("/home/hermes/.hermes/.env")
    prefix = "MINIMAX_CN_API_KEY="
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(prefix):
                api_key = line[len(prefix):].strip()
                break
    if not api_key:
        print(f"  [ERROR] MINIMAX_CN_API_KEY not found in env")
        return None

    payload = {
        "model": "image-01",
        "prompt": image_prompt,
        "aspect_ratio": "16:9",
        "n": 1,
    }
    req = urllib.request.Request(
        "https://api.minimaxi.com/v1/image_generation",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        image_urls = data.get("data", {}).get("image_urls", [])
        if not image_urls:
            print(f"  [ERROR] no image_urls in response")
            return None
        with urllib.request.urlopen(image_urls[0], timeout=60) as img_resp:
            image_bytes = img_resp.read()
        image_path.write_bytes(image_bytes)
        print(f"  [OK] generated {image_path.name} ({len(image_bytes)//1024} KB)")
        return image_path
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  [ERROR] MiniMax HTTP {e.code}: {body}")
        return None
    except Exception as e:
        print(f"  [ERROR] MiniMax: {e}")
        return None

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=3, help="Max recipes to publish per run")
    p.add_argument("--skip-image-check", action="store_true",
                   help="Skip hero image existence check (for testing render only)")
    args = p.parse_args()

    load_env()

    if not DB_PATH.exists():
        print(f"[ERROR] SQLite not found: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    pending = get_unpublished(conn)
    if not pending:
        print(f"[INFO] no unpublished validated recipes in DB")
        return 0

    print(f"=== Publishing {len(pending)} candidates (limit={args.limit}) ===")
    published_titles = get_published_titles()
    print(f"  Currently {len(published_titles)} recipes published on site")

    published_count = 0
    rejected_count = 0
    skipped_count = 0
    to_commit_paths: list[Path] = []

    for r in pending[:args.limit]:
        rid = r["id"]
        title = r["title"]
        slug = r["slug"]
        print(f"\n--- id={rid}  '{title}' ---")
        print(f"  slug: {slug}")

        # Dedup check
        ok, reason = check_dedup(slug, title, published_titles)
        if not ok:
            print(f"  [REJECTED] {reason}")
            if not args.dry_run:
                mark_rejected(conn, rid, reason)
            rejected_count += 1
            continue

        # Image check (P26)
        image_prompt = r["image_prompt"] or ""
        if not image_prompt and not args.skip_image_check:
            print(f"  [REJECTED] missing image_prompt (cannot generate image)")
            if not args.dry_run:
                mark_rejected(conn, rid, "missing image_prompt")
            rejected_count += 1
            continue

        image_path = generate_image(image_prompt, slug, args.dry_run)
        if image_path is None and not args.skip_image_check and not args.dry_run:
            print(f"  [SKIP] image not present, caller must generate before commit")
            skipped_count += 1
            continue

        # Render markdown
        md_content = render_markdown(r, slug)
        jekyll_filename = f"{TODAY}-{slug}.md"
        md_path = RECIPES_DIR / jekyll_filename
        if args.dry_run:
            print(f"  [DRY] would write {md_path} ({len(md_content)} bytes)")
        else:
            md_path.write_text(md_content, encoding="utf-8")
            print(f"  [OK] wrote {md_path.name} ({len(md_content)} bytes)")
            to_commit_paths.append(md_path)
            mark_published(conn, rid)
            published_titles.append(title)  # update in-memory for next iteration
            published_count += 1

    # Git commit + push
    if to_commit_paths:
        git_commit_push(args.dry_run)

    print(f"\n=== Summary ===")
    print(f"  Published: {published_count}")
    print(f"  Rejected (dedup/validation): {rejected_count}")
    print(f"  Skipped (missing image): {skipped_count}")
    return 0

if __name__ == "__main__":
    sys.exit(main())