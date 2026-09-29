#!/usr/bin/env python3
"""W96: Generate 5 Pinterest pin image variants per recipe via MiniMax image-01.

Strategy (per PinPinterest + RecipeKit 2026):
- 5 pins per recipe × 80 recipes = 400 unique pin images
- Aspect ratio 2:3 (1000x1500) — Pinterest's optimal vertical pin
- 5 angle variants per recipe:
  1. Hero overhead (default)
  2. Plate angle 45°
  3. Hands holding dish (lifestyle)
  4. Ingredients flat-lay
  5. Pinterest recipe card style (text overlay template)

Output: `_assets/pins/<slug>-N.jpg` per recipe (5 each)
Cost: ~15s per image × 5 × 82 recipes = ~102 minutes total
Pinterest save button URL: documented in README + pin pack markdown

Idempotent: Skips recipes that already have 5 pin variants.
Skip flag: Set SKIP_PIN_GEN=1 to disable (e.g. for testing).
"""

import os
import re
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

RECIPES_DIR = Path(__file__).resolve().parents[1] / '_recipes'
PINS_DIR = Path(__file__).resolve().parents[1] / '_assets' / 'pins'
PINS_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = os.environ.get('MINIMAX_CN_BASE_URL', 'https://api.minimax.chat').rstrip('/')
API_KEY = os.environ.get('MINIMAX_CN_API_KEY')

if not API_KEY:
    env_path = Path('/home/hermes/.hermes/.env')
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith('MINIMAX_CN_API_KEY='):
                API_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")
                break

if not API_KEY:
    print("❌ MINIMAX_CN_API_KEY not set")
    sys.exit(1)

assert API_KEY is not None  # for type checker

ASPECT = '2:3'  # Pinterest optimal vertical
VARIANTS = [
    ('hero', 'Overhead flat-lay food photography, bright natural light, rustic wooden table, appetizing plating, magazine-quality, {title}, {cuisine} cuisine, {protein} protein'),
    ('plate', '45-degree angle plate shot, white ceramic plate, garnish, steam visible, restaurant-style plating, {title}, {cuisine}'),
    ('hands', 'Lifestyle hands holding a warm bowl, cozy kitchen background, soft window light, {title}, {cuisine}, comfort food aesthetic'),
    ('ingredients', 'Flat-lay of fresh ingredients arranged on marble surface, herbs and spices in small bowls, overhead shot, recipe ingredients, {title}, Mediterranean ingredients'),
    ('recipe-card', 'Recipe card mockup with handwritten title overlay, styled food photo, Pinterest aesthetic, {calories} calories, {protein}g protein, ready in {total_time} min, {title}'),
]

def parse_fm(text):
    m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ':' in line and not line.startswith('  ') and not line.startswith('-'):
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm

def detect_protein(title, tags):
    """Detect main protein from title + tags."""
    text = (title + ' ' + tags).lower()
    for protein in ['chicken', 'salmon', 'shrimp', 'cod', 'turkey', 'beef',
                    'lamb', 'tofu', 'lentils', 'chickpeas', 'white beans',
                    'scallops', 'swordfish', 'halibut', 'fish', 'pasta']:
        if protein in text:
            return protein
    return 'mixed'

def generate_pin_image(slug, variant_name, prompt, max_retries=2):
    """Generate 1 pin image via MiniMax image-01 API."""
    out_path = PINS_DIR / f"{slug}-{variant_name}.jpg"
    if out_path.exists() and out_path.stat().st_size > 50000:
        return True, "exists"

    payload = json.dumps({
        'model': 'image-01',
        'prompt': prompt[:1500],  # API limit
        'aspect_ratio': ASPECT,
        'n': 1,
        'response_format': 'url',
    }).encode('utf-8')

    url = f'{API_BASE}/v1/image_generation'

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={
                    'Authorization': 'Bearer ' + API_KEY,
                    'Content-Type': 'application/json',
                }
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                result = json.loads(r.read().decode('utf-8'))
            # Per P97: response is data.image_urls[0], NOT image_url
            image_url = result['data']['image_urls'][0]

            # Download immediately (URL expires in ~24h per P97)
            with urllib.request.urlopen(image_url, timeout=60) as img_r:
                out_path.write_bytes(img_r.read())

            if out_path.stat().st_size > 50000:
                return True, f"generated {out_path.stat().st_size}B"
            return False, f"too small: {out_path.stat().st_size}B"
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
            if attempt + 1 >= max_retries:
                return False, f"error after {max_retries} retries: {e}"
            time.sleep(3)
    return False, "exhausted retries"

def process_recipe(md_path):
    """Generate 5 pin variants for one recipe."""
    text = md_path.read_text(encoding='utf-8')
    fm = parse_fm(text)
    if not fm:
        return False, "no frontmatter"

    m = re.match(r'(\d{4})-(\d{2})-(\d{2})-(.+)\.md', md_path.name)
    if not m:
        return False, "filename parse fail"
    slug = m.group(4)

    protein = detect_protein(fm.get('title', ''), fm.get('tags', ''))
    context = {
        'title': fm.get('title', 'recipe')[:100],
        'cuisine': fm.get('cuisine', 'Mediterranean'),
        'protein': protein,
        'calories': fm.get('calories', '400'),
        'protein_g': fm.get('protein', '20'),
        'total_time': fm.get('total_time', '30'),
    }

    results = []
    for variant_name, prompt_template in VARIANTS:
        prompt = prompt_template.format(**context)
        ok, msg = generate_pin_image(slug, variant_name, prompt)
        results.append((variant_name, ok, msg))

    success = sum(1 for _, ok, _ in results if ok)
    return success == len(VARIANTS), f"{success}/{len(VARIANTS)} variants"

def main():
    if os.environ.get('SKIP_PIN_GEN') == '1':
        print("⚠️ SKIP_PIN_GEN=1, skipping")
        sys.exit(0)

    recipes = sorted(RECIPES_DIR.glob('*.md'))
    print(f"Generating pin packs for {len(recipes)} recipes...")
    print(f"Aspect: {ASPECT}, Variants: {len(VARIANTS)}")
    print(f"Total images: {len(recipes) * len(VARIANTS)}")
    print()

    full_success = 0
    partial = 0
    failed = 0

    for md in recipes:
        ok, msg = process_recipe(md)
        if ok:
            full_success += 1
            print(f"✅ {md.name[:50]}: {msg}")
        elif '/' in msg and not msg.startswith('0/'):
            partial += 1
            print(f"⚠️ {md.name[:50]}: {msg}")
        else:
            failed += 1
            print(f"❌ {md.name[:50]}: {msg}")

    print(f"\n=== SUMMARY ===")
    print(f"Full success: {full_success}")
    print(f"Partial: {partial}")
    print(f"Failed: {failed}")

if __name__ == '__main__':
    main()
