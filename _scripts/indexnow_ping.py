#!/usr/bin/env python3
"""W100 (2026-11-19): IndexNow pinger for waimind.com.

Bing / Yandex / Seznam instant-indexing protocol. The site has ZERO Bing
indexation (verified 2026-11-19: site:waimind.com = 0 results), so every new
or changed URL should be pushed the moment it deploys instead of waiting for
organic crawler discovery (which for a zero-authority domain can take weeks).

Usage:
    python3 indexnow_ping.py                 # push all URLs changed in last 24h
    python3 indexnow_ping.py --full          # push every sitemap URL (first run)
    python3 indexnow_ping.py --urls URL1 URL2
    python3 indexnow_ping.py --dry-run

Key file: /9157e2a1b4c3d6e8f5a9b0c1d2e3f4a7.txt at site root (already committed).
IndexNow rules: >=1 URL -> GET with keylocation or POST JSON. Batching: all
URLs in one POST (limit 10,000 per request, we have ~200).
Protocol: https://www.indexnow.org/documentation
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
import urllib.error
from pathlib import Path

SITE = "https://waimind.com"
KEY = "9157e2a1b4c3d6e8f5a9b0c1d2e3f4a7"
KEY_FILE_NAME = f"{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"  # shared endpoint: routes to Bing+Yandex+Seznam
SITEMAP = "/home/hermes/healthy-recipes-site/_site/sitemap.xml"
LOCAL_SITEMAP_FALLBACK = None  # _site only exists after local build; live fetch used otherwise


def urls_from_live_sitemap() -> list[str]:
    req = urllib.request.Request(f"{SITE}/sitemap.xml", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    return [u for u in (l.split("<loc>")[1].split("</loc>")[0].strip()
                        for l in body.splitlines() if "<loc>" in l) if u]


def urls_changed_last_hours(hours: int) -> list[str]:
    """URLs whose recipe md file was modified in the last N hours (git + mtime)."""
    import subprocess
    since = (dt.datetime.now() - dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
    changed: list[str] = []
    try:
        r = subprocess.run(
            ["git", "-C", "/home/hermes/healthy-recipes-site", "log",
             "--since", since, "--name-only", "--format="],
            capture_output=True, text=True, timeout=30)
        files = set(f for f in r.stdout.splitlines() if f.startswith("_recipes/"))
    except Exception:
        files = set()
    for f in sorted(files):
        # _recipes/2026-11-18-slug.md -> /2026/11/18/slug/
        stem = Path(f).stem
        parts = stem.split("-", 3)
        if len(parts) >= 4:
            y, m, d, slug = parts
            changed.append(f"{SITE}/{y}/{m}/{d}/{slug}/")
    return changed


def ping(urls: list[str], dry_run: bool = False) -> tuple[int, str]:
    if not urls:
        return 0, "no URLs to ping"
    payload = {
        "host": "waimind.com",
        "key": KEY,
        "keyLocation": f"{SITE}/{KEY_FILE_NAME}",
        "urlList": urls[:10000],
    }
    if dry_run:
        return len(urls), f"DRY-RUN would POST {len(urls)} URLs to {ENDPOINT}"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "Mozilla/5.0 (compatible; waimind-indexnow/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return len(urls), f"HTTP {r.status} (IndexNow accepts 200/202)"
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:200]
        return len(urls), f"HTTP {e.code}: {detail}"
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="push every sitemap URL")
    ap.add_argument("--hours", type=int, default=24, help="changed-window (default 24h)")
    ap.add_argument("--urls", nargs="*", help="explicit URL list")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.urls:
        urls = args.urls
    elif args.full:
        urls = urls_from_live_sitemap()
    else:
        urls = urls_changed_last_hours(args.hours)

    n, msg = ping(urls, args.dry_run)
    print(f"[indexnow] {n} URLs | {msg}")
    for u in urls[:12]:
        print(f"  {u}")
    if n > 12:
        print(f"  ... +{n-12} more")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
