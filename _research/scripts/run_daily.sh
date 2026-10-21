#!/bin/bash
# _research/scripts/run_daily.sh — Cron wrapper for full research pipeline.
#
# Per AGENTS.md:
# 0 4 * * * /home/hermes/healthy-recipes-site/_research/scripts/run_daily.sh
#
# Pipeline:
# 1. fetch_recipes.py  (BBC + EatingWell)
# 2. adapt_recipes.py  (LLM transformation)
# 3. ingest_to_db.py   (SQLite + markdown export)
#
# Cron context has no shell env, so explicitly source Hermes .env for LLM key.

set -euo pipefail

# Load env (cron context has no shell env, explicitly source from Hermes .env)
if [ -f /home/hermes/.hermes/.env ]; then
    set -a
    source /home/hermes/.hermes/.env
    set +a
fi

PROJECT_ROOT="/home/hermes/healthy-recipes-site"
RESEARCH="${PROJECT_ROOT}/_research"
LOG_DIR="${RESEARCH}/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/run-${TIMESTAMP}.log"

mkdir -p "${LOG_DIR}"

cd "${PROJECT_ROOT}"

echo "=== Recipe Research Daily Pipeline ===" | tee -a "${LOG_FILE}"
echo "Date: $(date)" | tee -a "${LOG_FILE}"

# Step 1/3: Fetch raw
echo "[1/3] Fetching recipes..." | tee -a "${LOG_FILE}"
/home/hermes/apps/hermes-agent/venv/bin/python3 _research/scripts/fetch_recipes.py \
    --count 5 --source both 2>&1 | tee -a "${LOG_FILE}" || echo "  [WARN] fetch had errors" | tee -a "${LOG_FILE}"

# Step 2/3: LLM adapt
echo "[2/3] Adapting via LLM..." | tee -a "${LOG_FILE}"
/home/hermes/apps/hermes-agent/venv/bin/python3 _research/scripts/adapt_recipes.py \
    --count 5 2>&1 | tee -a "${LOG_FILE}" || echo "  [WARN] adapt had errors" | tee -a "${LOG_FILE}"

# Step 3/3: Ingest to DB + markdown export
echo "[3/4] Ingesting to SQLite + markdown..." | tee -a "${LOG_FILE}"
/home/hermes/apps/hermes-agent/venv/bin/python3 _research/scripts/ingest_to_db.py 2>&1 | tee -a "${LOG_FILE}" || echo "  [WARN] ingest had errors" | tee -a "${LOG_FILE}"

# Step 4/4: Auto-publish validated recipes to live Jekyll site
# (P26 invariant: hero image is generated inline via MiniMax API;
#  P44 invariant: dedup check rejects collisions with existing _recipes/ titles;
#  publishes up to 3 recipes per cron run to avoid quota spikes.)
echo "[4/4] Publishing validated recipes to site..." | tee -a "${LOG_FILE}"
/home/hermes/apps/hermes-agent/venv/bin/python3 _research/scripts/publish_to_site.py --limit 3 2>&1 | tee -a "${LOG_FILE}" || echo "  [WARN] publish had errors" | tee -a "${LOG_FILE}"

echo "=== Pipeline complete — recipes published to https://healthy-recipes-site.pages.dev/ ===" | tee -a "${LOG_FILE}"

# Step 5/5 (W96, 2026-10-21): worktree hygiene.
# This pipeline used to leave modified _research/ scripts + log.md uncommitted,
# which poisoned the 03:00 daily recipe pipeline: its `git pull --rebase` aborted
# under `set -e`, so the push never ran and the live site froze for 20 days.
# Commit our own artifacts here so the worktree is clean for the next cron.
echo "[5/5] Committing research artifacts (W96 worktree hygiene)..." | tee -a "${LOG_FILE}"
git add _research/scripts/ _research/wiki/ .gitignore 2>/dev/null || true
if git diff --cached --quiet; then
    echo "  no research changes to commit" | tee -a "${LOG_FILE}"
else
    git commit -m "[research] $(date +%Y-%m-%d) — daily research wiki update" 2>&1 | tee -a "${LOG_FILE}" || true
    git -c rebase.autoStash=true pull --rebase origin main 2>&1 | tee -a "${LOG_FILE}" || true
    git push origin main 2>&1 | tee -a "${LOG_FILE}" || echo "  [WARN] research push failed (non-fatal)" | tee -a "${LOG_FILE}"
fi
