#!/usr/bin/env python3
"""W97 (2026-10-21): generate a Facebook posting pack for waimind.com recipes.

Why Facebook: Food Blogger Pro's 2024→2026 traffic comparison of Pinch of Yum
showed Facebook growing from 0.57% → 6.42% of blog traffic — an 11x increase —
after they started posting consistently (~3x/day). Food content is practical
and shareable, which suits Facebook's feed better than it suits Pinterest.

Output:
  _scripts/facebook-post-pack.md   — human-readable, copy-paste ready
  _scripts/facebook-schedule.csv   — for Meta Business Suite / Buffer import

Two ways to use it:
  1. MANUAL (works today, no credentials): open the .md, copy a post into the
     Facebook Page composer, attach the hero image, publish.
  2. AUTOMATED (needs setup): a Facebook Page + Page access token with
     pages_manage_posts. See FACEBOOK-SETUP.md notes in the pack footer.

Post style notes for Facebook:
  - First line must hook — Facebook truncates after ~2 lines ("See more").
  - Keep the caption short; long recipe text belongs on the site.
  - Put the link at the end, after the value.
  - 3-5 hashtags max (Facebook weights them far less than Instagram).
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "_recipes"
HEROES = ROOT / "assets" / "recipes"
SITE = "https://waimind.com"
MD_OUT = Path(__file__).resolve().parent / "facebook-post-pack.md"
CSV_OUT = Path(__file__).resolve().parent / "facebook-schedule.csv"

POSTS_PER_DAY = 3
SLOTS = ["08:00", "12:30", "18:00"]

HOOKS = [
    "Dinner sorted for tonight 👇",
    "Save this one for your next weeknight 🍽️",
    "This is what 30 minutes looks like 😍",
    "High protein, low effort. Here's how 👇",
    "If you're bored of the same dinners, try this 🔥",
    "One pan, no fuss, big flavour 👇",
    "Making this again tonight — it never misses ✨",
]


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


def first_sentence(text: str, limit: int = 150) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s", text)
    out = parts[0] if parts else text
    if len(out) > limit:
        out = out[: limit - 1].rstrip() + "…"
    return out


rows = []
for f in sorted(RECIPES.glob("*.md"), reverse=True):
    fm = parse(f)
    if not fm.get("_slug"):
        continue
    hero = HEROES / f"{fm['_slug']}.jpg"
    rows.append({
        "slug": fm["_slug"],
        "title": fm.get("title", "Recipe"),
        "intro": first_sentence(fm.get("description", "")),
        "calories": fm.get("calories", ""),
        "protein": fm.get("protein", ""),
        "total_time": fm.get("total_time", ""),
        "cuisine": fm.get("cuisine", ""),
        "link": fm["_url"],
        "hero_local": str(hero) if hero.exists() else "",
        "hero_url": f"{SITE}/assets/recipes/{fm['_slug']}.jpg",
    })

start = dt.date.today() + dt.timedelta(days=1)
for i, r in enumerate(rows):
    r["date"] = (start + dt.timedelta(days=i // POSTS_PER_DAY)).isoformat()
    r["time"] = SLOTS[i % POSTS_PER_DAY]
    r["hook"] = HOOKS[i % len(HOOKS)]
    stats = []
    if r["calories"]:
        stats.append(f"{r['calories']} kcal")
    if r["protein"]:
        stats.append(f"{r['protein']}g protein")
    if r["total_time"]:
        stats.append(f"{r['total_time']} min")
    r["caption"] = (
        f"{r['hook']}\n\n"
        f"{r['title']}\n"
        f"{r['intro']}\n\n"
        f"📊 {' · '.join(stats)}\n"
        f"Get the full recipe 👉 {r['link']}\n\n"
        f"#healthyrecipes #mediterraneandiet #lowcalorie #highprotein"
    )

with CSV_OUT.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["date", "time", "caption", "hero_url", "hero_local", "link"])
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in w.fieldnames})

md = [
    "# Waimind Facebook Post Pack",
    "",
    f"Auto-generated: {dt.datetime.now():%Y-%m-%d %H:%M} HKT",
    f"Posts: **{len(rows)}** · {POSTS_PER_DAY}/day from {start}",
    "",
    "## Why Facebook",
    "",
    "Pinch of Yum's traffic went from **0.57% → 6.42%** from Facebook between 2024",
    "and 2026 (an 11x increase) after posting ~3x/day.",
    "(source: foodbloggerpro.com/blog/pinch-of-yums-traffic-trends-2024-vs-2026)",
    "",
    "## How to use",
    "",
    "**Manual (works now, no setup):** open your Facebook Page → create post →",
    "copy a caption below → attach the hero image (local path given) → publish.",
    "",
    "**Automated:** needs a Facebook Page + a Page access token with",
    "`pages_manage_posts` (requires Meta App Review). Once 老闆 provides a token",
    "we can post via `POST /{page-id}/photos` with `url=` + `caption=`.",
    "",
    "## First 12 posts",
    "",
]

for r in rows[:12]:
    md.append(f"### {r['date']} {r['time']} — {r['title']}")
    md.append("")
    md.append("```")
    md.append(r["caption"])
    md.append("```")
    md.append(f"- hero image: `{r['hero_local'] or r['hero_url']}`")
    md.append("")

MD_OUT.write_text("\n".join(md), encoding="utf-8")
print(f"✅ {MD_OUT}")
print(f"✅ {CSV_OUT} ({len(rows)} rows)")
print(f"   {POSTS_PER_DAY}/day from {start} → ends "
      f"{(start + dt.timedelta(days=(len(rows)-1)//POSTS_PER_DAY))}")
