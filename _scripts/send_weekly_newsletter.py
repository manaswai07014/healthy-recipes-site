#!/usr/bin/env python3
"""W94: Weekly newsletter via Buttondown API.

Every Saturday 09:00 HKT, sends "This week's 3 new recipes" email
to waimind Buttondown subscribers.

Buttondown API: https://api.buttondown.email/v1/
- POST /emails  (send a scheduled email)
- Requires BUTTONDOWN_API_KEY in /home/hermes/.hermes/.env

Cron (added separately):
  0 9 * * 6  python3 /home/hermes/healthy-recipes-site/_scripts/send_weekly_newsletter.py
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

RECIPES_DIR = Path(__file__).resolve().parents[1] / '_recipes'
ENV_FILE = Path('/home/hermes/.hermes/.env')
BUTTONDOWN_API = 'https://api.buttondown.email/v1'


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_weeks_recipes():
    """Recipes published in the last 7 days (max 5, prioritise newest)."""
    cutoff = datetime.now() - timedelta(days=7)
    recipes = []
    for md in sorted(RECIPES_DIR.glob('*.md')):
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})-(.+)\.md', md.name)
        if not m:
            continue
        y, mo, d, slug = m.groups()
        try:
            pub_date = datetime(int(y), int(mo), int(d))
        except ValueError:
            continue
        if pub_date < cutoff:
            continue
        text = md.read_text(encoding='utf-8')
        fm = {}
        fm_match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).splitlines():
                if ':' in line and not line.startswith('  '):
                    k, v = line.split(':', 1)
                    fm[k.strip()] = v.strip().strip('"')
        title = fm.get('title', slug.replace('-', ' ').title())
        subtitle = fm.get('subtitle') or fm.get('description', '')
        if len(subtitle) > 140:
            subtitle = subtitle[:137] + '...'
        recipes.append({
            'title': title,
            'subtitle': subtitle,
            'calories': fm.get('calories', '?'),
            'protein': fm.get('protein', '?'),
            'total_time': fm.get('total_time', '?'),
            'url': f'https://waimind.com/{y}/{mo}/{d}/{slug}/',
        })
    # newest first, cap at 5
    recipes.reverse()
    return recipes[:5]


def build_email(recipes):
    if not recipes:
        return None
    date_str = datetime.now().strftime('%B %d, %Y')
    n = len(recipes)
    subject = f'{n} new healthy recipes this week 🍅'
    lines = [
        '# This Week at Waimind Kitchen',
        '',
        f'*{date_str} — {n} new low-calorie Mediterranean recipes*',
        '',
    ]
    for r in recipes:
        lines.append(f'## [{r["title"]}]({r["url"]})')
        lines.append('')
        lines.append(f'{r["subtitle"]}')
        lines.append('')
        lines.append(f'**{r["calories"]} kcal · {r["protein"]}g protein · {r["total_time"]} min**')
        lines.append('')
        lines.append(f'[Read the full recipe →]({r["url"]})')
        lines.append('')
        lines.append('---')
        lines.append('')
    lines.append('## Grab the free 7-day meal plan')
    lines.append('')
    lines.append('[Download the 7-Day Mediterranean Meal Plan (PDF)](https://waimind.com/assets/downloads/7-day-mediterranean-meal-plan.html) — every meal 400-600 kcal with 15g+ protein.')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('Thanks for cooking with us. See you next Saturday! 🌿')
    lines.append('')
    lines.append('*Waimind Kitchen — [waimind.com](https://waimind.com)*')
    return subject, '\n'.join(lines)


def send_email(subject, body, api_key):
    payload = json.dumps({
        'subject': subject,
        'body': body,
        'email_type': 'public',  # send to all subscribers
        'publish_date': datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
    }).encode()
    req = urllib.request.Request(
        f'{BUTTONDOWN_API}/emails',
        data=payload,
        headers={
            'Authorization': f'Token {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return True, result
    except urllib.error.HTTPError as e:
        return False, f'HTTP {e.code}: {e.read().decode()[:300]}'
    except Exception as e:
        return False, f'{type(e).__name__}: {e}'


def main():
    load_env()
    api_key = os.environ.get('BUTTONDOWN_API_KEY', '')
    if not api_key:
        print('❌ BUTTONDOWN_API_KEY not set in ~/.hermes/.env')
        print('   老闆: Buttondown → Settings → API → copy key → add to /home/hermes/.hermes/.env as BUTTONDOWN_API_KEY=...')
        sys.exit(1)

    recipes = get_weeks_recipes()
    print(f'Recipes published in last 7 days: {len(recipes)}')
    if not recipes:
        print('No new recipes this week — skipping send.')
        sys.exit(0)

    for r in recipes:
        print(f'  - {r["title"]}')

    subject, body = build_email(recipes)
    assert subject and body
    print(f'\nSubject: {subject}')
    print(f'Body length: {len(body)} chars\n')

    ok, result = send_email(subject, body, api_key)
    if ok:
        print(f'✅ Email sent! ID: {result.get("id", "?")}')
    else:
        print(f'❌ Send failed: {result}')
        sys.exit(1)


if __name__ == '__main__':
    main()
