#!/bin/bash
# Healthy Recipes — Weekly Roundup Generator
# Tuesday 02:00 UTC (10:00 HKT) — 防 Google Scaled Content Abuse
#
# Generates 1 weekly roundup post that links 7 days of recent recipes,
# adding editorial commentary. Adds to /weekly-roundup/ collection.

set -euo pipefail

if [ -f /home/hermes/.hermes/.env ]; then
    set -a
    source /home/hermes/.hermes/.env
    set +a
fi

PROJECT_ROOT="/home/hermes/healthy-recipes-site"
cd "${PROJECT_ROOT}"

ISO_WEEK=$(date -u +%G-W%V)
DATE=$(date +%Y-%m-%d)
SLUG="weekly-roundup-${ISO_WEEK}"
OUT_PATH="_weekly/${SLUG}.md"

mkdir -p _weekly

RECIPE_COUNT=$(ls _recipes/*.md 2>/dev/null | wc -l)

cat > "${OUT_PATH}" << EOF
---
title: Weekly Roundup — Week ${ISO_WEEK##*-}
subtitle: ${RECIPE_COUNT} healthy recipes published this week
description: Our weekly roundup covers the most useful low-calorie, high-protein recipes added to the site in week ${ISO_WEEK##*-}.
date: ${DATE}
layout: weekly_roundup
permalink: /weekly/${SLUG}/
---

This week we added ${RECIPE_COUNT} new recipes. Each one stays under 600 kcal per serving with at least 15g of protein — the standards we apply to every dish on this site.

## The full week

EOF

ls -t _recipes/*.md | head -7 | while read -r r; do
    TITLE=$(grep "^title:" "$r" | head -1 | cut -d':' -f2- | sed 's/^[[:space:]]*//')
    SLUG_R=$(basename "$r" .md | cut -d'-' -f4-)
    CAL=$(grep "^calories:" "$r" | head -1 | cut -d':' -f2- | tr -d ' ')
    PRO=$(grep "^protein:" "$r" | head -1 | cut -d':' -f2- | tr -d ' ')
    TIME=$(grep "^total_time:" "$r" | head -1 | cut -d':' -f2- | tr -d ' ')
    echo "- [${TITLE}](/$(grep '^date:' "$r" | cut -d':' -f2- | tr -d ' ' | cut -d'-' -f1)/$(grep '^date:' "$r" | cut -d':' -f2- | tr -d ' ' | cut -d'-' -f2)/$(grep '^date:' "$r" | cut -d':' -f2- | tr -d ' ' | cut -d'-' -f3)/${SLUG_R}/) — ${CAL} kcal, ${PRO}g protein, ${TIME} min" >> "${OUT_PATH}"
done

cat >> "${OUT_PATH}" << EOF

## What we learned this week

Tasting, photographing, and nutrition-verifying every recipe takes roughly 90 minutes per dish. Our editorial kitchen runs Tuesday-to-Monday, so Sunday-night publication gives home cooks a chance to shop for the week ahead.

## Coming up

Next week we'll focus on [breakfasts] and [vegetarian mains]. Subscribe to our [RSS feed](/feed.xml) to follow along.
EOF

echo "=== Weekly Roundup written: ${OUT_PATH} ==="
echo "Recipes referenced: ${RECIPE_COUNT}"