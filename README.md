# Healthy Western Recipes

Low-calorie Mediterranean and Western recipes, every serving 400-600 kcal with at least 15g protein.

## Stack
- Jekyll 4.3 + jekyll-seo-tag + jekyll-sitemap + jekyll-feed + jekyll-paginate
- Cloudflare Pages (free hosting + auto-build from gh-pages branch)
- Python content pipeline (LLM-powered recipe generator)

## Local dev
```bash
bundle install
bundle exec jekyll serve --livereload
# Open http://localhost:4000
```

## Deploy
```bash
git push origin main
git subtree split --prefix=. -b gh-pages-tmp
git push --force origin gh-pages-tmp:gh-pages
```

## Content pipeline
See `_scripts/` for the daily recipe generator. It uses MiniMax-M2 to produce recipe JSON + Markdown in the format defined by `references/recipe-json-schema.md`.

## Source attribution
Recipes are inspired by:
- BBC Good Food (https://www.bbcgoodfood.com)
- EatingWell (https://www.eatingwell.com)

Every recipe is rewritten and tested. All trademarks belong to their owners.