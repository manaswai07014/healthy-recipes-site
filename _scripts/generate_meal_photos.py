#!/usr/bin/env python3
"""
W87: Generate 28 meal photos for 7-Day Mediterranean Meal Plan.
Reuses generate_hero_image pipeline from generate_recipe.py.

Output: /home/hermes/healthy-recipes-site/assets/recipes/meal-plan/<slug>.jpg
Each photo: 1280x720 JPEG, ~300KB, 16:9 aspect ratio.

Usage:
  python3 _scripts/generate_meal_photos.py
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_scripts"))

# Source env for MiniMax key
env_file = Path("/home/hermes/.hermes/.env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from generate_recipe import generate_hero_image, LLM_API_KEY

OUT_DIR = ROOT / "assets" / "recipes" / "meal-plan"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 28 meal prompts (Day 1-7 × Breakfast/Lunch/Snack/Dinner)
MEALS = [
    # ── Day 1: Mediterranean Monday ──
    (1, "breakfast", "Greek yogurt power bowl with mixed berries, honey, granola, almond butter and chia seeds, white marble countertop, soft morning light, shallow depth of field"),
    (1, "lunch", "Golden chickpea couscous bowl with cucumber, cherry tomatoes, parsley, mint, tahini-lemon dressing, overhead shot, rustic wooden table, bright natural light"),
    (1, "snack", "Mediterranean snack plate with apple, raw almonds, dark chocolate square, linen napkin, minimalist styling, soft shadows"),
    (1, "dinner", "Tuscan white bean kale ribollita soup in white bowl, slice of whole-grain sourdough bread on side, grated parmesan, olive oil drizzle, warm kitchen lighting"),

    # ── Day 2: Tuscan Tuesday ──
    (2, "breakfast", "Mediterranean veggie scramble with three eggs, spinach, feta cheese, cherry tomatoes, served on plate with whole-grain toast, bright morning light"),
    (2, "lunch", "Mediterranean chickpea cucumber salad in glass bowl with red onion, cherry tomatoes, feta crumbles, lemon-tahini dressing, fresh herbs on top"),
    (2, "snack", "Pear and walnut halves on small ceramic plate, simple healthy snack styling, soft focus background"),
    (2, "dinner", "Mediterranean fisherman seafood soup with tomato broth, white fish, shrimp, mussels, in shallow bowl with crusty bread, rustic kitchen setting"),

    # ── Day 3: Seafood Wednesday ──
    (3, "breakfast", "Smoked salmon avocado toast on whole-grain sourdough, capers, lemon slice, cracked black pepper, minimalist plating on white plate"),
    (3, "lunch", "Mediterranean garlic shrimp cauliflower rice bowl with roasted red peppers, tzatziki drizzle, fresh dill, overhead shot on rustic wooden table"),
    (3, "snack", "Carrot sticks and hummus in small bowl, healthy Mediterranean snack, soft natural light"),
    (3, "dinner", "Mediterranean shrimp pasta with white wine garlic sauce, cherry tomatoes, parsley, parmesan, served in shallow pasta bowl"),

    # ── Day 4: Chicken Thursday ──
    (4, "breakfast", "Mediterranean egg white omelet with sun-dried tomatoes, feta, spinach, served with slice of rye toast, bright kitchen morning light"),
    (4, "lunch", "Mediterranean chicken tray bake with feta, zucchini, bell pepper, olive oil, served on sheet pan, warm rustic styling"),
    (4, "snack", "Small Greek yogurt bowl with honey drizzle and cinnamon sprinkle, minimalist snack styling"),
    (4, "dinner", "Mediterranean chicken spanakorizo with spinach rice, side mixed greens salad with feta and olive oil, served in clay bowl"),

    # ── Day 5: Pantry Friday ──
    (5, "breakfast", "Overnight oats Mediterranean style in mason jar with figs, walnuts, honey drizzle, chia seeds, morning kitchen light"),
    (5, "lunch", "Italian turkey stuffed bell peppers with melted mozzarella on top, served on plate with side arugula salad, rustic Italian kitchen styling"),
    (5, "snack", "Hard-boiled egg sliced in half with whole-grain crackers, simple healthy Mediterranean snack on wooden board"),
    (5, "dinner", "Burrata and burst cherry tomato pasta with fresh basil, cracked pepper, served in shallow white bowl, Mediterranean table styling"),

    # ── Day 6: Plant-Forward Saturday ──
    (6, "breakfast", "Purple berry almond smoothie bowl topped with granola and sliced almonds, served in ceramic bowl with spoon, bright overhead light"),
    (6, "lunch", "Spiced chickpea couscous bowl with tangy tahini drizzle, cucumber, tomatoes, fresh herbs, Mediterranean lunch styling on wooden table"),
    (6, "snack", "Small banana with natural peanut butter drizzle, simple Mediterranean snack on plate"),
    (6, "dinner", "Vegetarian sushi grain bowl with brown rice quinoa, edamame, avocado, cucumber, cabbage, nori strips, sesame seeds, Asian-Mediterranean fusion styling"),

    # ── Day 7: Sunday Reset ──
    (7, "breakfast", "Mediterranean berry protein bowl with Greek yogurt, mixed berries, honey-toasted granola, slivered almonds, drizzle of honey, bright morning styling"),
    (7, "lunch", "Lemon herb baked salmon over orzo with spinach and cherry tomatoes, olive oil drizzle, served on white plate with lemon slices"),
    (7, "snack", "Apple with almond butter dip on small plate, simple Sunday snack styling"),
    (7, "dinner", "Mediterranean baked cod with tomato caper olive sauce, served with cauliflower mash and roasted vegetables, elegant plating on white plate"),
]


def main():
    if not LLM_API_KEY:
        print("ERROR: MINIMAX_CN_API_KEY not set in /home/hermes/.hermes/.env")
        sys.exit(1)

    print(f"=== W87: Generating {len(MEALS)} meal photos ===\n")
    print(f"Output: {OUT_DIR}\n")

    success = 0
    failed = []

    for day, meal_type, prompt in MEALS:
        slug = f"day-{day}-{meal_type}"
        print(f"[{day}/{len(MEALS)}] Day {day} {meal_type}: ", end="", flush=True)

        try:
            # generate_hero_image saves to assets/recipes/<slug>.jpg — but we need custom dir
            # Use the underlying API directly with our path
            payload = json.dumps({
                "model": "image-01",
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "n": 1,
                "response_format": "url",
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.minimaxi.com/v1/image_generation",
                data=payload,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())

            # Extract image URL
            image_url = None
            if "data" in result and "image_urls" in result["data"]:
                image_url = result["data"]["image_urls"][0]
            elif "image_url" in result:
                image_url = result["image_url"]

            if not image_url:
                failed.append((slug, "no image_url in response"))
                print(f"FAIL (no URL)")
                continue

            # Download image
            with urllib.request.urlopen(image_url, timeout=30) as img_resp:
                image_data = img_resp.read()

            # Save to meal-plan dir
            output_path = OUT_DIR / f"{slug}.jpg"
            output_path.write_bytes(image_data)
            size_kb = len(image_data) // 1024
            print(f"OK ({size_kb}KB)")
            success += 1

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()[:200]
            failed.append((slug, f"HTTP {e.code}: {error_body}"))
            print(f"FAIL (HTTP {e.code})")
        except Exception as e:
            failed.append((slug, f"{type(e).__name__}: {str(e)[:100]}"))
            print(f"FAIL ({type(e).__name__})")

    print(f"\n=== Summary ===")
    print(f"Success: {success}/{len(MEALS)}")
    if failed:
        print(f"Failed:")
        for slug, reason in failed:
            print(f"  - {slug}: {reason}")

    return 0 if success == len(MEALS) else 1


if __name__ == "__main__":
    sys.exit(main())