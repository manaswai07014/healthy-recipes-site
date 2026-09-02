# AGENTS.md — Recipe Research Wiki

## Purpose
Daily cron-driven wiki that fetches recipes from BBC Good Food and EatingWell,
adapts them through LLM (translation to in-house editorial style + nutrition
validation), and stores both as SQLite (queryable) + Markdown (readable).

## Source attribution policy
Recipes are FETCHED from BBC Good Food and EatingWell, ADAPTED by our
editorial kitchen (transformation, not reproduction), and PUBLISHED on
our Jekyll site with proper transformation marks.

Per 老闆's direction (2026-09-02):
1. Fetch full original content (title, URL, ingredients, instructions)
2. LLM adapts (rebrand to our style, validate 400-600 kcal / ≥15g protein,
   rewrite any verbatim long passages, add chef tips, regenerate nutrition)
3. Published recipes on healthy-recipes-site show "Developed, tested, and
   nutrition-verified by our editorial kitchen" — NO BBC/EatingWell attribution
4. Wiki `_research/` retains source URL + original content + adapted content
   for audit trail only (NOT published)

## Directory layout
```
_research/
├── AGENTS.md             (this file)
├── wiki/
│   ├── index.md          master index
│   ├── log.md            APPEND-ONLY operation journal
│   ├── bbc/              BBC Good Food adapted recipes
│   ├── eatingwell/       EatingWell adapted recipes
│   └── templates/
│       └── recipe-page.md  markdown export template
├── data/
│   ├── recipes.db        SQLite WAL mode (queriable)
│   └── backups/          daily snapshot
├── scripts/
│   ├── fetch_recipes.py  scrape BBC + EatingWell (5-10/day target)
│   ├── adapt_recipes.py  LLM adaptation (transformation)
│   ├── ingest_to_db.py   SQLite + markdown export
│   ├── run_daily.sh      cron wrapper
│   └── qa/
│       └── run_all.py    daily QA suite
├── raw/                  raw scraped HTML cache (gitignored)
├── adapted/              LLM-adapted JSON intermediate (gitignored)
└── logs/                 cron + per-script logs
```

## Hard rules
1. NEVER copy verbatim long passages from source — always transform
2. NEVER publish BBC/EatingWell attribution on healthy-recipes-site (P27)
3. ALWAYS validate nutrition (400-600 kcal, ≥15g protein) before commit
4. Source URL + original snapshot retained in SQLite only (audit trail)
5. Adapted recipes that don't meet nutrition criteria → marked `rejected`
   in DB but NOT published to site

## Operations

### !fetch [N]
Run `scripts/fetch_recipes.py` immediately. Args: N = number of recipes
to fetch per source (default 5).

### !adapt [N]
Run `scripts/adapt_recipes.py`. LLM transforms raw → adapted JSON.

### !ingest
Run `scripts/ingest_to_db.py`. SQLite insert + markdown export.

### !daily
Full pipeline: fetch → adapt → ingest → QA.

### !qa
Run daily QA: count new today, validate nutrition, check published recipes
match wiki entries, log to log.md.

### !logview [N]
Show last N lines of wiki/log.md (default 20).

### !status
brief / total / today count / QA status / DB size.

## Session startup
1. Read wiki/log.md (last 20 entries)
2. Read wiki/index.md
3. !status
4. Show today's pending fetch + adapt queue

## Cron
0 4 * * * /home/hermes/healthy-recipes-site/_research/scripts/run_daily.sh
→ 12:00 HKT daily, 1 hour after CarMotion (0 0) + 1 hour before healthy-recipes (0 3)
+ offset avoids LLM quota contention

## Reference docs
- healthy-recipes-site skill (parent project)
- SKILL.md: healthy-recipes-site (this wiki's parent context)
- car-evolution-project/AGENTS.md (Karpathy LLM Wiki template inspiration)
