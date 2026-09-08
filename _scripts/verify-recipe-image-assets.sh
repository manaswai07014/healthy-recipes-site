#!/bin/bash
# scripts/verify-recipe-image-assets.sh
# P45 Layer 2 pre-flight gate (2026-09-03 NEW)
#
# Purpose: Verify all _recipes/*.md frontmatter `hero_image:` paths
#          point to real local files in assets/recipes/.
#          Exit 1 if any missing → cron abort, do NOT commit broken frontmatter.
#
# Usage: bash scripts/verify-recipe-image-assets.sh
#        or:  python3 _scripts/verify_recipe_image_assets.py
#
# Cron wrapper integration (run BEFORE git add):
#   bash scripts/verify-recipe-image-assets.sh || { echo "ABORT: missing image assets"; exit 1; }
#
# Author: 惠惠 (P45 enforcement hook)
# Date: 2026-09-03

set -euo pipefail

# Resolve skill-relative path
# P66 fix: SITE_DIR must point to PROJECT root, not skill root.
# Skill lives at ~/.hermes/skills/media/healthy-recipes-site/scripts/
# but PROJECT lives at /home/hermes/healthy-recipes-site/
# Allow override via HEALTHY_RECIPES_ROOT env, default to canonical project location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE_DIR="${HEALTHY_RECIPES_ROOT:-/home/hermes/healthy-recipes-site}"
cd "${SITE_DIR}"

RECIPES_DIR="_recipes"
ASSETS_DIR="assets/recipes"

if [ ! -d "${RECIPES_DIR}" ]; then
    echo "❌ ${RECIPES_DIR}/ not found in ${SITE_DIR}"
    exit 2
fi

recipe_count=$(ls "${RECIPES_DIR}"/*.md 2>/dev/null | wc -l)
if [ "$recipe_count" -eq 0 ]; then
    echo "⚠️  No recipe markdown files in ${RECIPES_DIR}/, skipping"
    exit 0
fi

echo "🔍 P45 image asset gate: verifying ${recipe_count} recipe(s)..."
echo ""

missing=()
no_field=()

for md in "${RECIPES_DIR}"/*.md; do
    # Extract hero_image path from YAML frontmatter (handle quoted + unquoted)
    hero=$(grep -oE '^hero_image:\s*"?\S+?"?' "$md" 2>/dev/null | head -1 | sed -E 's/^hero_image:\s*"?//;s/"?$//')
    
    if [ -z "$hero" ]; then
        no_field+=("$md")
        continue
    fi
    
    # Skip external URLs (http/https) — those are handled differently
    if [[ "$hero" =~ ^https?:// ]]; then
        echo "⏭️  $(basename "$md") → external URL: $hero"
        continue
    fi
    
    # Convert /assets/recipes/foo.jpg → assets/recipes/foo.jpg
    asset_rel="${hero#/}"
    asset_path="${SITE_DIR}/${asset_rel}"
    
    if [ ! -f "$asset_path" ]; then
        missing+=("$(basename "$md") → $hero")
        echo "❌ MISSING: $(basename "$md") → $hero"
    else
        # Optional: verify it's a real image (magic bytes)
        magic=$(file -b --mime-type "$asset_path" 2>/dev/null || echo "unknown")
        if [[ ! "$magic" =~ ^image/ ]]; then
            missing+=("$(basename "$md") → $hero (not image: $magic)")
            echo "❌ NOT-IMAGE: $(basename "$md") → $hero (mime=$magic)"
        else
            size=$(stat -c%s "$asset_path" 2>/dev/null || stat -f%z "$asset_path" 2>/dev/null || echo 0)
            echo "✅ $(basename "$md") → $hero ($magic, ${size}B)"
        fi
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ${#missing[@]} -gt 0 ]; then
    echo "❌ FAIL: ${#missing[@]} recipe(s) have broken hero_image"
    echo ""
    echo "Affected recipes:"
    printf '  • %s\n' "${missing[@]}"
    echo ""
    echo "Remediation options:"
    echo "  1. Run: python3 _scripts/regenerate_recipe_image.py <slug>"
    echo "  2. Manually gen image via MiniMax text-to-image + save to assets/recipes/"
    echo "  3. Revert last cron commit: git revert HEAD"
    echo ""
    echo "ABORT: cron pipeline should NOT commit broken frontmatter."
    exit 1
fi

if [ ${#no_field[@]} -gt 0 ]; then
    echo "⚠️  WARN: ${#no_field[@]} recipe(s) have no hero_image field:"
    printf '  • %s\n' "${no_field[@]}"
    echo ""
fi

echo "✅ PASS: all ${recipe_count} recipe(s) have valid hero_image assets"
echo ""