#!/usr/bin/env python3
"""W97 (2026-10-21): Real traffic report for waimind.com from CF Web Analytics.

Queries the Cloudflare GraphQL Analytics API (RUM dataset populated by the
beacon that _layouts/default.html injects). This is the ONLY traffic source
that gives real numbers — Google Search Console lags weeks and the site had
zero measurement before W97.

Usage:
    python3 fetch_traffic_stats.py                 # last 7 days, human summary
    python3 fetch_traffic_stats.py --days 30
    python3 fetch_traffic_stats.py --telegram      # also send to 老闆
    python3 fetch_traffic_stats.py --json          # machine-readable

Credentials: CF_API_TOKEN from /home/hermes/.cfenv (account-scoped cfat_ token
— works on GraphQL, returns 401 on /user/tokens/verify; that is expected).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path

CFENV = Path("/home/hermes/.cfenv")
HERMES_ENV = Path("/home/hermes/.hermes/.env")
ACCOUNT_ID = "b3e5ac003d206366f1a64379801164e2"
SITE_TAG = "596fc83bdc884f8fad557fe42a889bb1"
GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"


def _read_kv(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _gql(query: str, token: str) -> dict:
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        GRAPHQL, data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode())


def fetch(days: int = 7) -> dict:
    token = _read_kv(CFENV, "CF_API_TOKEN")
    if not token:
        raise RuntimeError("CF_API_TOKEN not found in /home/hermes/.cfenv")

    today = dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    f = f'siteTag: "{SITE_TAG}", date_geq: "{start.isoformat()}", date_leq: "{today.isoformat()}"'

    q = ('{ viewer { accounts(filter: {accountTag: "%s"}) { '
         'byDay: rumPageloadEventsAdaptiveGroups(limit: 100, filter: {%s}, orderBy: [date_ASC]) '
         '{ count dimensions { date requestHost } } '
         'byPath: rumPageloadEventsAdaptiveGroups(limit: 20, filter: {%s}, orderBy: [count_DESC]) '
         '{ count dimensions { requestPath } } '
         '} } }' % (ACCOUNT_ID, f, f))

    d = _gql(q, token)
    if d.get("errors"):
        raise RuntimeError(f"GraphQL errors: {json.dumps(d['errors'])[:300]}")

    accts = ((d.get("data") or {}).get("viewer") or {}).get("accounts") or []
    by_day, by_path = [], []
    for a in accts:
        for g in a.get("byDay") or []:
            by_day.append({"date": (g.get("dimensions") or {}).get("date"), "count": g.get("count") or 0})
        for g in (a.get("byPath") or []):
            by_path.append({"path": (g.get("dimensions") or {}).get("requestPath"), "count": g.get("count") or 0})
    total = sum(r["count"] for r in by_day)
    return {"days": days, "start": start.isoformat(), "end": today.isoformat(),
            "total": total, "by_day": by_day, "by_path": by_path}


def render(stats: dict) -> str:
    days = stats["days"]
    total = stats["total"]
    per_day = total / days if days else 0
    lines = [
        f"📊 waimind.com traffic — last {days} days",
        f"({stats['start']} → {stats['end']})",
        "",
        f"Pageviews: {total}  (~{per_day:.1f}/day)",
        "",
    ]
    if stats["by_day"]:
        lines.append("By day:")
        for r in stats["by_day"]:
            bar = "▇" * min(r["count"], 20)
            lines.append(f"  {r['date']}  {r['count']:>4}  {bar}")
    else:
        lines.append("By day: (no beacon data yet)")
    if stats["by_path"]:
        lines.append("")
        lines.append("Top pages:")
        for r in stats["by_path"][:10]:
            lines.append(f"  {r['count']:>4}  {r['path']}")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    tok = _read_kv(HERMES_ENV, "TELEGRAM_BOT_TOKEN")
    chat = _read_kv(HERMES_ENV, "TELEGRAM_HOME_CHANNEL") or "6394565017"
    if not tok:
        print("[WARN] TELEGRAM_BOT_TOKEN missing, skipping send")
        return False
    data = json.dumps({"chat_id": chat, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{tok}/sendMessage",
        data=data, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            out = json.loads(r.read().decode())
        return bool(out.get("ok"))
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] telegram send failed: {exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    stats = fetch(args.days)
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print(render(stats))
    if args.telegram:
        ok = send_telegram(render(stats))
        print(f"\n[telegram] {'sent ✅' if ok else 'NOT sent ❌'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
