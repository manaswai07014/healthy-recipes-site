#!/usr/bin/env python3
"""
W82: Cross-domain redirect via account-level Bulk Redirects (CF official method)
================================================================================

CF Pages 官方文檔 (custom-domains > "Disable access to *.pages.dev subdomain")
明確講: 要 redirect *.pages.dev → custom domain, 用 account-level Bulk Redirect.

之前用 zone-level Page Rules 一直失敗, 因為:
  - Page Rules 只 match 自己 zone 嘅 domain (waimind.com)
  - healthy-recipes-site.pages.dev 唔屬於 waimind.com zone

Bulk Redirects 係 account-level, 可以 match *.pages.dev。

3 個 steps (跟官方 create-api 文檔):
  1. Create a Bulk Redirect List (kind="redirect")
  2. Add redirect items (source_url -> target_url)
  3. Create a Bulk Redirect Rule (ruleset phase http_request_redirect)

Required token permissions:
  - Account > Bulk URL Redirects > Edit (Mass URL Redirects Write)
  - Account > Account Filter Lists > Edit
  - Account > Account Rulesets Write (or Select Configuration Write)

Usage:
  python3 w82_bulk_redirect.py --token TOKEN --account ACCOUNT_ID
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

PARSER = argparse.ArgumentParser(description="W82 Bulk Redirect: pages.dev → waimind.com")
PARSER.add_argument("--token", required=True, help="Cloudflare API token")
PARSER.add_argument("--account", required=True, help="Cloudflare Account ID")
ARGS = PARSER.parse_args()

BASE = "https://api.cloudflare.com/client/v4"
HEADERS = {
    "Authorization": f"Bearer {ARGS.token}",
    "Content-Type": "application/json",
}

LIST_NAME = "w82_pages_dev_redirect"
OLD_HOST = "healthy-recipes-site.pages.dev"
NEW_HOST = "waimind.com"

def api(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        print(f"  ✗ HTTP {e.code}: {raw[:400]}")
        return None
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {e}")
        return None

def step1_create_list():
    print("=== Step 1: Create Bulk Redirect List ===")
    res = api("POST", f"/accounts/{ARGS.account}/rules/lists", {
        "name": LIST_NAME,
        "description": "W82: redirect healthy-recipes-site.pages.dev → waimind.com",
        "kind": "redirect",
    })
    if res and res.get("success"):
        list_id = res["result"]["id"]
        print(f"  ✓ List created: {list_id}")
        return list_id
    print("  (List may already exist, trying to find it)")
    # Try list existing
    res2 = api("GET", f"/accounts/{ARGS.account}/rules/lists")
    if res2 and res2.get("success"):
        for l in res2.get("result", []):
            if l.get("name") == LIST_NAME:
                print(f"  ✓ Found existing list: {l['id']}")
                return l["id"]
    return None

def step2_add_items(list_id):
    print("\n=== Step 2: Add redirect items ===")
    # CF Bulk Redirect: 用 subpath_matching + preserve_path_suffix 代替 wildcard
    items = [
        {
            "redirect": {
                "source_url": f"{OLD_HOST}/",
                "target_url": f"https://{NEW_HOST}/",
                "status_code": 301,
                "subpath_matching": True,
                "preserve_path_suffix": True,
                "preserve_query_string": True,
            }
        },
    ]
    res = api("POST", f"/accounts/{ARGS.account}/rules/lists/{list_id}/items", items)
    if res and res.get("success"):
        op_id = res["result"]["operation_id"]
        print(f"  ✓ Items submitted, operation_id={op_id}")
        # Wait for completion
        for _ in range(30):
            time.sleep(2)
            st = api("GET", f"/accounts/{ARGS.account}/rules/lists/bulk_operations/{op_id}")
            if st and st.get("success"):
                if st["result"]["status"] == "completed":
                    print(f"  ✓ Operation completed")
                    return True
        print("  ⚠ Operation timed out")
        return False
    return False

def step3_create_rule(list_id):
    print("\n=== Step 3: Create Bulk Redirect Rule (ruleset) ===")
    # The redirect rule references the list
    rule = {
        "name": "W82 redirect ruleset",
        "kind": "root",
        "phase": "http_request_redirect",
        "rules": [{
            "ref": "w82_redirect",
            "expression": f"http.request.full_uri in ${LIST_NAME}",
            "description": "W82: pages.dev → waimind.com",
            "action": "redirect",
            "action_parameters": {
                "from_list": {
                    "name": LIST_NAME,
                    "key": "http.request.full_uri"
                }
            }
        }]
    }
    res = api("POST", f"/accounts/{ARGS.account}/rulesets", rule)
    if res and res.get("success"):
        print(f"  ✓ Ruleset created: {res['result']['id']}")
        return True
    print("  ✗ Ruleset creation failed (may already exist, need PUT not POST)")
    return False

def verify():
    print("\n=== Verify ===")
    time.sleep(10)
    test = f"https://{OLD_HOST}/2026/09/12/mediterranean-shrimp-pasta-with-white-wine/"
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        req = urllib.request.Request(test, method="HEAD")
        with opener.open(req, timeout=15) as r:
            status, loc = r.status, r.headers.get("Location", "(none)")
    except urllib.error.HTTPError as e:
        status, loc = e.code, e.headers.get("Location", "(none)")
    print(f"  {test}")
    print(f"  → {status} → {loc}")
    if status == 301 and NEW_HOST in loc:
        print("  ✓ REDIRECT WORKING")
        return True
    print("  ⚠ Not yet (propagation 30-60s)")
    return False

def main():
    print("=" * 60)
    print(f"W82: {OLD_HOST} → {NEW_HOST} (account-level Bulk Redirect)")
    print("=" * 60)
    list_id = step1_create_list()
    if not list_id:
        print("✗ Abort: no list id")
        sys.exit(1)
    if not step2_add_items(list_id):
        print("✗ Abort: items failed")
        sys.exit(1)
    step3_create_rule(list_id)
    verify()

if __name__ == "__main__":
    main()