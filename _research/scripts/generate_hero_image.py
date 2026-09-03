#!/usr/bin/env python3
"""
generate_hero_image.py — Generate hero image for a research wiki recipe via MiniMax API.

Usage:
    python3 generate_hero_image.py --prompt "..." --output /path/to/output.jpg
    python3 generate_hero_image.py --recipe-id 1  # reads image_prompt + slug from SQLite

Cron context loads /home/hermes/.hermes/.env (MINIMAX_CN_API_KEY).

Endpoint verified 2026-09-03:
    POST https://api.minimaxi.com/v1/image_generation
    Headers: Authorization: Bearer *** + Content-Type: application/json
    Body: {"model": "image-01", "prompt": "...", "aspect_ratio": "16:9", "n": 1}
    Response: {"id": "...", "data": {"image_urls": ["https://..."]}}

Image URL expires in ~24h (signed OSS URL), so download immediately.
"""
from __future__ import annotations
import argparse, json, os, sqlite3, sys, urllib.request, urllib.error
from pathlib import Path

RESEARCH = Path("/home/hermes/healthy-recipes-site/_research")
DB_PATH = RESEARCH / "data" / "recipes.db"
ASSETS_RECIPES = Path("/home/hermes/healthy-recipes-site/assets/recipes")
IMAGE_ENDPOINT = "https://api.minimaxi.com/v1/image_generation"

def load_api_key() -> str:
    env_file = Path("/home/hermes/.hermes/.env")
    for line in env_file.read_text().splitlines():
        if line.startswith("MINIMAX_CN_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("MINIMAX_CN_API_KEY not found in /home/hermes/.hermes/.env")

def generate(prompt: str, output_path: Path) -> bool:
    """Call MiniMax image gen API, download URL, save as JPG. Return True on success."""
    api_key = load_api_key()
    payload = {
        "model": "image-01",
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "n": 1,
    }
    req = urllib.request.Request(
        IMAGE_ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  [ERROR] MiniMax API HTTP {e.code}: {body}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [ERROR] MiniMax API: {e}", file=sys.stderr)
        return False

    image_urls = data.get("data", {}).get("image_urls", [])
    if not image_urls:
        print(f"  [ERROR] no image_urls in response: {json.dumps(data)[:300]}", file=sys.stderr)
        return False

    image_url = image_urls[0]
    # Download (signed URL expires in ~24h, download immediately)
    try:
        with urllib.request.urlopen(image_url, timeout=60) as img_resp:
            image_bytes = img_resp.read()
    except Exception as e:
        print(f"  [ERROR] failed to download image: {e}", file=sys.stderr)
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    size_kb = len(image_bytes) // 1024
    print(f"  [OK] saved {output_path.name} ({size_kb} KB)")
    return True

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", help="Direct prompt (skips SQLite)")
    p.add_argument("--output", help="Output path (used with --prompt)")
    p.add_argument("--recipe-id", type=int, help="DB id; reads image_prompt + slug from SQLite")
    args = p.parse_args()

    if args.recipe_id is not None:
        if not DB_PATH.exists():
            print(f"[ERROR] DB not found: {DB_PATH}", file=sys.stderr)
            return 1
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT image_prompt, slug FROM recipes WHERE id=?", (args.recipe_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            print(f"[ERROR] recipe id={args.recipe_id} not found", file=sys.stderr)
            return 1
        image_prompt, slug = row
        if not image_prompt:
            print(f"[ERROR] recipe id={args.recipe_id} has no image_prompt", file=sys.stderr)
            return 1
        output_path = ASSETS_RECIPES / f"{slug}.jpg"
    elif args.prompt and args.output:
        output_path = Path(args.output)
        image_prompt = args.prompt
    else:
        print("[ERROR] provide --recipe-id OR --prompt + --output", file=sys.stderr)
        return 1

    if output_path.exists():
        print(f"  [SKIP] {output_path.name} already exists")
        return 0

    success = generate(image_prompt, output_path)
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())