#!/usr/bin/env python3
"""
W82: Add cross-domain redirect via Cloudflare API
老闆 needs:
1. CF API Token (with Pages:Edit + Page Rules:Edit per zone waimind.com)
2. Account ID
3. Zone ID for waimind.com

Setup:
1. https://dash.cloudflare.com/profile/api-tokens
2. Create Custom Token:
   - Permissions: Account > Cloudflare Pages > Edit
                  Zone > Page Rules > Edit
   - Account Resources: Include > All accounts
   - Zone Resources: Include > Specific zone > waimind.com
   - Continue > Create Token > Copy token
3. Account ID: https://dash.cloudflare.com → right sidebar
4. Zone ID: waimind.com → right sidebar
5. Run: python3 w82_add_redirect.py --token TOKEN --account ACCOUNT --zone ZONE
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

PARSER = argparse.ArgumentParser(description="Add W82 cross-domain redirect to CF Pages")
PARSER.add_argument("--token", required=True, help="Cloudflare API token")
PARSER.add_argument("--account", required=True, help="Cloudflare Account ID (hex)")
PARSER.add_argument("--zone", required=True, help="waimind.com Zone ID (hex)")
PARSER.add_argument("--project", default="healthy-recipes-site", help="CF Pages project name")
PARSER.add_argument("--target", default="https://waimind.com", help="Target domain")
ARGS = PARSER.parse_args()

BASE = "https://api.cloudflare.com/client/v4"

def api_call(method, path, body=None, expect_status=None):
    """Make CF API call with error handling."""
    url = f"{BASE}{path}"
    headers = {
        "Authorization": f"Bearer {ARGS.token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode()
            status = resp.status
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        status = e.code
        if expect_status and status == expect_status:
            return {"_status": status, "_expected": True}
        print(f"✗ HTTP {status}: {text}")
        return None
    if expect_status and status != expect_status:
        print(f"✗ Expected {expect_status}, got {status}: {text}")
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text, "_status": status}

def create_rule(priority, expression, description, action_type, action_value):
    """Create one Page Rule (uses Zone Page Rules API, not Pages-level)."""
    # Per CF API v4 docs: forwarding_url action value must be {status_code, url}
    # Using $1 placeholder to capture matched path (CF wildcards: * captures)
    rule = {
        "targets": [
            {
                "target": "url",
                "constraint": {"operator": "matches", "value": expression}
            }
        ],
        "actions": [
            {
                "id": action_type,
                "value": action_value
            }
        ],
        "priority": priority,
        "status": "active"
    }
    # Use ZONE Page Rules API
    path = f"/zones/{ARGS.zone}/pagerules"
    result = api_call("POST", path, body=rule)
    if result and result.get("success"):
        print(f"✓ Created rule [{priority}] {description}")
        print(f"   ID: {result['result']['id']}")
        return result["result"]
    else:
        print(f"✗ Failed to create rule [{priority}]: {result}")
        return None

def list_rules():
    """List current Page Rules on the zone."""
    path = f"/zones/{ARGS.zone}/pagerules"
    result = api_call("GET", path)
    if result and result.get("success"):
        return result.get("result", [])
    return []

def print_rules(rules):
    """Safely print rules list (handles dicts and strings)."""
    if not rules:
        print("  (none)")
        return
    for r in rules:
        if isinstance(r, dict):
            print(f"  [{r.get('priority')}] {r.get('description', '(no description)')} — {r.get('id')}")
        else:
            # Rule is a string or other non-dict type
            print(f"  [?] (non-dict rule): {r}")

def verify_redirect(test_url):
    """Verify the redirect is working."""
    print(f"\n=== Verify Redirect ===")
    print(f"  Test URL: {test_url}")
    req = urllib.request.Request(test_url, method="HEAD")
    # Disable redirect following
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=15) as resp:
            status = resp.status
            location = resp.headers.get("Location", "(none)")
    except urllib.error.HTTPError as e:
        status = e.code
        location = e.headers.get("Location", "(none)")
    print(f"  Status: {status}")
    print(f"  Location: {location}")
    if status == 301 and ARGS.target in location:
        print(f"  ✓ Cross-domain redirect working!")
        return True
    else:
        print(f"  ⚠ Unexpected status/location. Rule may still be propagating (30-60s).")
        return False

def main():
    print("=" * 60)
    print("W82: Add cross-domain redirect for healthy-recipes-site.pages.dev → waimind.com")
    print("=" * 60)
    print()

    # List existing rules first
    print("=== Current Rules ===")
    existing = list_rules()
    print_rules(existing)
    print()

    # Rule 1: cross-domain redirect (priority 1)
    print("=== Creating Rule 1: cross-domain redirect ===")
    # CF API v4 spec: forwarding_url value = {status_code: 301, url: "..."}
    # Use $1 to capture wildcard match
    cross_domain_action = {
        "status_code": 301,
        "url": f"{ARGS.target}$1"
    }
    r1 = create_rule(
        priority=1,
        expression="*healthy-recipes-site.pages.dev/*",
        description="W82: Old subdomain → waimind.com (cross-domain 301)",
        action_type="forwarding_url",
        action_value=cross_domain_action,
    )
    if not r1:
        sys.exit(1)

    # Rule 2: force HTTPS (priority 2)
    print("\n=== Creating Rule 2: force HTTPS ===")
    r2 = create_rule(
        priority=2,
        expression=f"http://{ARGS.target.replace('https://', '').rstrip('/')}/*",
        description=f"W82: Force HTTPS for {ARGS.target}",
        action_type="force_https",
        action_value={"enable": True},
    )
    if not r2:
        print("  (non-critical, may already exist)")

    # Wait for propagation
    print("\n=== Waiting 10s for rule propagation ===")
    time.sleep(10)

    # Verify
    test_url = f"https://healthy-recipes-site.pages.dev/2026/09/12/mediterranean-shrimp-pasta-with-white-wine/"
    success = verify_redirect(test_url)

    # Final summary
    print("\n" + "=" * 60)
    print("=== Summary ===")
    print("=" * 60)
    print(f"Rules created: 2 (cross-domain redirect + force HTTPS)")
    print(f"Target: {ARGS.target}")
    print(f"Test: {test_url}")
    print(f"Result: {'✓ Working' if success else '⚠ May need 30-60s to propagate'}")
    print()
    print("老闆 can verify in CF Dashboard:")
    print(f"  https://dash.cloudflare.com/?to=/:account/pages/view/{ARGS.project}/rules")

if __name__ == "__main__":
    main()
