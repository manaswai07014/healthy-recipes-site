#!/usr/bin/env python3
"""W94: Generate Pinterest pin pack for all recipes.
Output: _scripts/pinterest-pin-pack.md (boss copy-pastes to Pinterest)
"""
import re
from pathlib import Path

RECIPES_DIR = Path(__file__).resolve().parents[1] / '_recipes'
OUT = Path(__file__).resolve().parent / 'pinterest-pin-pack.md'

recipes = []
for md in sorted(RECIPES_DIR.glob('*.md')):
    text = md.read_text(encoding='utf-8')
    fm = {}
    fm_match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not fm_match:
        continue
    for line in fm_match.group(1).splitlines():
        if ':' in line and not line.startswith('  '):
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip().strip('"')
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})-(.+)\.md', md.name)
    if m:
        y, mo, d, slug = m.groups()
        recipes.append({
            'title': fm.get('title', slug.replace('-', ' ').title()),
            'calories': fm.get('calories', '?'),
            'protein': fm.get('protein', '?'),
            'total_time': fm.get('total_time', '?'),
            'cuisine': fm.get('cuisine', 'Mediterranean'),
            'url': f'https://waimind.com/{y}/{mo}/{d}/{slug}/',
            'slug': slug,
        })

lines = [
    '# Waimind Pinterest Pin Pack',
    '',
    f'Auto-generated: {len(recipes)} pins',
    '',
    '## Strategy (Fresh Cup of Joy empirical data)',
    '- Pin 10-15/day is the sweet spot (their #1 traffic source)',
    '- First 40 chars of description matter most for Pinterest search',
    '- Boards: Low Calorie Recipes / Mediterranean Diet / High Protein Meals / Quick Dinners',
    '- Each pin links back to the recipe page on waimind.com',
    '',
]

for i, r in enumerate(recipes, 1):
    pin_title = r['title'][:90]
    pin_desc = (
        f"{r['title']} — only {r['calories']} calories with {r['protein']}g protein, "
        f"ready in {r['total_time']} minutes. Easy {r['cuisine']} recipe for healthy "
        f"weeknight dinners. #lowcalorie #highprotein #mediterraneandiet #healthyrecipes"
    )
    lines.append(f'---')
    lines.append(f'### Pin {i}: {pin_title}')
    lines.append(f'')
    lines.append(f'- **URL**: {r["url"]}')
    lines.append(f'- **Image**: https://waimind.com/assets/recipes/{r["slug"]}.jpg')
    lines.append(f'- **Description**: {pin_desc}')
    lines.append(f'')

OUT.write_text('\n'.join(lines), encoding='utf-8')
print(f'Pin pack written: {OUT}')
print(f'Total pins: {len(recipes)}')
