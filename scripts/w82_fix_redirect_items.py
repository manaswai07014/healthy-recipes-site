#!/usr/bin/env python3
"""
W82: 修正 Bulk Redirect items — 用 subpath_matching 代替 wildcard
之前加咗兩條錯 items (帶 /*), 而家用正確參數重新加。
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error

PARSER = argparse.ArgumentParser()
PARSER.add_argument("--token", required=True)
PARSER.add_argument("--account", required=True)
PARSER.add_argument("--list-id", required=True, help="Bulk Redirect List ID (a652749b...)")
ARGS = PARSER.parse_args()

BASE = "https://api.cloudflare.com/client/v4"
HEADERS = {"Authorization": f"Bearer {ARGS.token}", "Content-Type": "application/json"}

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
        print(f"  ✗ HTTP {e.code}: {e.read().decode()[:300]}")
        return None

def main():
    print("=== 清除舊 items ===")
    # List existing items
    res = api("GET", f"/accounts/{ARGS.account}/rules/lists/{ARGS.list_id}/items")
    if not res or not res.get("success"):
        print("✗ 讀唔到 items")
        return

    items = res.get("result", [])
    print(f"  現有 {len(items)} 條 items")
    for i in items:
        print(f"    - id={i.get('id')} source={i.get('redirect', {}).get('source_url')}")

    # Delete all existing items
    item_ids = [i["id"] for i in items if i.get("id")]
    if item_ids:
        print(f"\n=== 刪除 {len(item_ids)} 條舊 items ===")
        for iid in item_ids:
            r = api("DELETE", f"/accounts/{ARGS.account}/rules/lists/{ARGS.list_id}/items/{iid}")
            if r and r.get("success"):
                print(f"  ✓ 刪除 {iid}")
            else:
                print(f"  ⚠ 刪除 fail {iid}")

    time.sleep(2)

    print("\n=== 加正確 items (subpath_matching + preserve_path_suffix) ===")
    new_items = [{
        "redirect": {
            "source_url": f"{OLD_HOST}/",
            "target_url": f"https://{NEW_HOST}/",
            "status_code": 301,
            "subpath_matching": True,
            "preserve_path_suffix": True,
            "preserve_query_string": True,
        }
    }]
    res2 = api("POST", f"/accounts/{ARGS.account}/rules/lists/{ARGS.list_id}/items", new_items)
    if res2 and res2.get("success"):
        op_id = res2["result"]["operation_id"]
        print(f"  ✓ Submitted operation_id={op_id}")
        for _ in range(30):
            time.sleep(2)
            st = api("GET", f"/accounts/{ARGS.account}/rules/lists/bulk_operations/{op_id}")
            if st and st.get("success") and st["result"]["status"] == "completed":
                print("  ✓ 完成")
                return
        print("  ⚠ timeout")
    else:
        print("  ✗ 加 items 失敗")
        if res2:
            print(f"  errors: {res2.get('errors')}")

if __name__ == "__main__":
    main()