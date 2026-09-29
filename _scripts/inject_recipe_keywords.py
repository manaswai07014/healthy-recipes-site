#!/usr/bin/env python3
"""W96: Inject `keywords:` frontmatter field into all recipes.

Strategy (per Member Kitchens SEO 2026 + TechnovaPartners 2026):
- Long-tail keywords (3-7 words) drive 70% of organic traffic
- 94.74% of all keywords have ≤10 monthly searches but compound
- Generate 8-12 keyword variants per recipe from:
  - cuisine (e.g. "italian")
  - category (e.g. "main")
  - protein (e.g. "chicken", "salmon", "tofu")
  - prep style (e.g. "30-minute", "one-pot", "sheet-pan")
  - dietary (e.g. "low-calorie", "high-protein", "mediterranean-diet")
  - cooking method (e.g. "baked", "grilled", "braised")
  - common search patterns ("easy", "healthy", "weeknight")

Output: Edits `_recipes/*.md` in place to add `keywords:` field
between `tags:` and `hero_image:` lines.

Bake: idempotent — running twice produces same result. Skips recipes
that already have `keywords:` field. Preserves all other frontmatter.
"""

import re
import sys
from pathlib import Path

RECIPES_DIR = Path(__file__).resolve().parents[1] / '_recipes'

# Long-tail keyword buckets (extracted from Member Kitchens SEO 2026
# + Real food blog search patterns)
TIME_KEYWORDS = {
    '15': '15-minute', '20': '20-minute', '25': '25-minute',
    '30': '30-minute', '35': '35-minute', '40': '40-minute',
    '45': '45-minute', '50': '50-minute', '60': '60-minute',
}

CUISINE_KEYWORDS = {
    'Italian': ['italian', 'italian-recipes', 'authentic-italian'],
    'Greek': ['greek', 'greek-recipes', 'mediterranean-greek'],
    'Mediterranean': ['mediterranean', 'mediterranean-diet', 'mediterranean-recipes'],
    'Spanish': ['spanish', 'spanish-recipes', 'tapas-style'],
    'French': ['french', 'french-recipes', 'provencal'],
    'Moroccan': ['moroccan', 'moroccan-recipes', 'north-african'],
    'Turkish': ['turkish', 'turkish-recipes', 'middle-eastern'],
    'Asian': ['asian', 'asian-inspired', 'asian-fusion'],
    'European': ['european', 'continental'],
    'American': ['american', 'american-style'],
}

PROTEIN_KEYWORDS = {
    'chicken': ['chicken-breast', 'boneless-chicken', 'chicken-thighs'],
    'salmon': ['salmon', 'salmon-fillet', 'salmon-recipes'],
    'shrimp': ['shrimp', 'prawns', 'seafood'],
    'cod': ['cod', 'white-fish', 'lean-fish'],
    'turkey': ['turkey', 'ground-turkey', 'lean-poultry'],
    'beef': ['beef', 'lean-beef', 'beef-recipes'],
    'lamb': ['lamb', 'lamb-recipes', 'greek-lamb'],
    'tofu': ['tofu', 'plant-protein', 'vegan-protein'],
    'lentils': ['lentils', 'lentil-recipes', 'plant-protein'],
    'chickpeas': ['chickpeas', 'garbanzo', 'plant-protein'],
    'white beans': ['white-beans', 'cannellini', 'plant-protein'],
    'scallops': ['scallops', 'seafood', 'premium-seafood'],
    'swordfish': ['swordfish', 'fish-recipes', 'mediterranean-fish'],
    'halibut': ['halibut', 'white-fish', 'premium-fish'],
    'fish': ['fish', 'fish-recipes', 'lean-protein'],
}

DIET_KEYWORDS = {
    'Low-Calorie': ['low-calorie', 'low-calorie-recipes', 'under-500-calories'],
    'High-Protein': ['high-protein', 'high-protein-recipes', 'protein-rich'],
    'Quick': ['quick-dinner', 'weeknight-dinner', 'easy-recipe'],
    'Mediterranean': ['mediterranean-diet', 'heart-healthy', 'mediterranean-meal'],
    'One-Pot': ['one-pot', 'one-pot-meal', 'easy-cleanup'],
    'Balanced': ['balanced-meal', 'nutritious', 'wholesome'],
    'Low-Carb': ['low-carb', 'low-carb-recipes', 'keto-friendly'],
    'Vegan': ['vegan', 'plant-based', 'vegan-recipes'],
    'Vegetarian': ['vegetarian', 'meatless', 'vegetarian-recipes'],
    'Sheet-Pan': ['sheet-pan', 'sheet-pan-dinner', 'easy-cleanup'],
    'High-Fiber': ['high-fiber', 'fiber-rich', 'gut-healthy'],
}

METHOD_KEYWORDS = {
    'baked': ['baked', 'oven-baked', 'easy-bake'],
    'grilled': ['grilled', 'grilling', 'charred'],
    'braised': ['braised', 'slow-cooked', 'tender-braised'],
    'roasted': ['roasted', 'oven-roasted', 'roasted-vegetables'],
    'sautéed': ['sauteed', 'pan-fried', 'stovetop'],
    'seared': ['seared', 'pan-seared', 'crispy'],
    'stewed': ['stewed', 'one-pot-stew', 'hearty-stew'],
    'poached': ['poached', 'gentle-cook', 'delicate'],
    'simmered': ['simmered', 'slow-simmer', 'flavorful-broth'],
}

INTENT_MODIFIERS = ['easy', 'healthy', 'best', 'simple', 'quick', 'authentic']

def parse_frontmatter(text):
    """Parse YAML frontmatter into dict."""
    m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ':' in line and not line.startswith('  ') and not line.startswith('-'):
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    body = text[m.end():]
    return fm, body

def generate_keywords(fm):
    """Generate 8-12 long-tail keywords from frontmatter fields."""
    keywords = []

    # Base descriptors (always)
    keywords.append(f"healthy {fm.get('cuisine', 'mediterranean').lower()} recipes")
    keywords.append(f"low calorie {fm.get('cuisine', 'mediterranean').lower()} dinner")

    # Cuisine-specific
    cuisine = fm.get('cuisine', '')
    if cuisine in CUISINE_KEYWORDS:
        keywords.extend(CUISINE_KEYWORDS[cuisine][:2])

    # Protein-specific (extract from title or tags)
    title_lower = fm.get('title', '').lower()
    tags_lower = fm.get('tags', '').lower()
    combined = title_lower + ' ' + tags_lower
    for protein, kws in PROTEIN_KEYWORDS.items():
        if protein in combined:
            keywords.extend(kws[:1])
            break  # only first protein match

    # Time-based
    total_time = fm.get('total_time', '')
    try:
        mins = int(total_time)
        if mins <= 30:
            keywords.append(f"quick {mins}-minute dinner")
            keywords.append(f"easy {mins}-minute recipe")
        elif mins <= 45:
            keywords.append(f"{mins}-minute weeknight dinner")
    except (ValueError, TypeError):
        pass

    # Diet tag-based
    diet_tags_raw = fm.get('diet_tags', '')
    # Strip brackets if present
    diet_tags = re.sub(r'[\[\]]', '', diet_tags_raw)
    for tag in [t.strip() for t in diet_tags.split(',')]:
        if tag in DIET_KEYWORDS:
            keywords.extend(DIET_KEYWORDS[tag][:2])

    # Method detection from title
    for method, kws in METHOD_KEYWORDS.items():
        if method in title_lower:
            keywords.extend(kws[:1])
            break

    # Category
    cat = fm.get('category', '').lower()
    if cat:
        keywords.append(f"{cat.lower()} course")
        keywords.append(f"{cat.lower()} dish")

    # Intent modifiers with cuisine
    if cuisine:
        keywords.append(f"easy {cuisine.lower()} dinner recipe")
        keywords.append(f"healthy {cuisine.lower()} {cat.lower() if cat else 'meal'}")

    # Deduplicate + limit to 12
    seen = set()
    unique = []
    for kw in keywords:
        kw = kw.lower().strip()
        if kw and kw not in seen:
            seen.add(kw)
            unique.append(kw)
        if len(unique) >= 12:
            break

    return unique

def inject_keywords_to_file(md_path):
    """Inject `keywords:` field into recipe frontmatter."""
    text = md_path.read_text(encoding='utf-8')

    # Skip if already has keywords
    if re.search(r'^keywords:', text, re.MULTILINE):
        return False, "already has keywords"

    fm, body = parse_frontmatter(text)
    if not fm:
        return False, "no frontmatter"

    keywords = generate_keywords(fm)
    if not keywords:
        return False, "no keywords generated"

    # Format as YAML list
    kw_yaml = "keywords:\n" + "\n".join(f"  - \"{kw}\"" for kw in keywords)

    # Find insertion point: after `tags:` line, before `hero_image:`
    # Pattern: locate tags line + any nested lines, then insert keywords after
    tags_match = re.search(r'^(tags:.*\n(?:  - .*\n)*)', text, re.MULTILINE)
    if tags_match:
        insert_pos = tags_match.end()
        new_text = text[:insert_pos] + kw_yaml + "\n" + text[insert_pos:]
    else:
        # Fallback: insert after last frontmatter line before ---
        lines = text.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('---') and i > 0:
                insert_idx = i
                break
        lines.insert(insert_idx, kw_yaml)
        new_text = '\n'.join(lines)

    md_path.write_text(new_text, encoding='utf-8')
    return True, f"added {len(keywords)} keywords"

def main():
    recipes = sorted(RECIPES_DIR.glob('*.md'))
    print(f"Scanning {len(recipes)} recipes...")

    success = 0
    skipped = 0
    failed = 0

    for md in recipes:
        ok, msg = inject_keywords_to_file(md)
        if ok:
            success += 1
            print(f"✅ {md.name[:50]}: {msg}")
        elif "already" in msg:
            skipped += 1
        else:
            failed += 1
            print(f"❌ {md.name[:50]}: {msg}")

    print(f"\nDone: {success} added, {skipped} skipped, {failed} failed")

if __name__ == '__main__':
    main()
