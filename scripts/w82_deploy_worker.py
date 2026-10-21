# W82: Deploy Cloudflare Worker for cross-domain redirect
# 老闆 needs:
# 1. CF API Token (Account.Workers:Edit + Account.Workers Scripts:Edit perms)
# 2. Account ID
#
# What this does:
# - Creates Worker named 'w82-cross-domain-redirect'
# - Deploys code that 301 redirects healthy-recipes-site.pages.dev/* → waimind.com/*
# - Adds route: healthy-recipes-site.pages.dev/* (zone=waimind.com) → worker
# - Result: 老 subdomain request → 301 → waimind.com

import argparse
import json
import sys
import urllib.request
import urllib.error
import time

PARSER = argparse.ArgumentParser(description="Deploy W82 Cloudflare Worker for cross-domain redirect")
PARSER.add_argument("--token", required=True, help="Cloudflare API token")
PARSER.add_argument("--account", required=True, help="Cloudflare Account ID (hex)")
PARSER.add_argument("--zone", required=True, help="waimind.com Zone ID (hex)")
ARGS = PARSER.parse_args()

BASE = "https://api.cloudflare.com/client/v4"
HEADERS = {
    "Authorization": f"Bearer {ARGS.token}",
    "Content-Type": "application/json",
}

WORKER_NAME = "w82-cross-domain-redirect"
TARGET_DOMAIN = "https://waimind.com"

WORKER_SCRIPT = """
// W82: Cross-domain redirect for healthy-recipes-site.pages.dev → waimind.com
addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Extract path + query string from old URL
  const newUrl = '""" + TARGET_DOMAIN + """' + url.pathname + url.search;
  // 301 Permanent Redirect (preserves SEO)
  return event.respondWith(new Response(null, {
    status: 301,
    headers: {
      'Location': newUrl,
      'Cache-Control': 'public, max-age=86400'  // 1 day cache for performance
    }
  }));
});
"""

def api_call(method, path, body=None):
    """Make CF API call."""
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ✗ HTTP {e.code}: {body[:300]}")
        return {"success": False, "error": body}
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}

def deploy_worker_script():
    """Step 1: Upload Worker script."""
    print("=== Step 1: Deploy Worker script ===")
    # Workers Scripts: PUT /accounts/{id}/workers/scripts/{script_name}
    path = f"/accounts/{ARGS.account}/workers/scripts/{WORKER_NAME}"
    # For script content, need to send as multipart/form-data or use specific JSON shape
    # CF API expects: {script: "code", bindings: [], main: {module: "..."}}
    body = {
        "main": {
            "name": "index",
            "content": WORKER_SCRIPT
        }
    }
    result = api_call("PUT", path, body=body)
    if result.get("success"):
        print(f"  ✓ Worker script deployed")
        return True
    else:
        print(f"  ✗ Failed: {result.get('errors', result)}")
        return False

def find_or_create_route():
    """Step 2: Add route so the worker handles the old subdomain."""
    print("\n=== Step 2: Add Worker route for healthy-recipes-site.pages.dev ===")
    
    # First, check if the domain is already added as a custom domain to Pages
    # (CF requires this so the route can be attached)
    # List current routes
    list_path = f"/zones/{ARGS.zone}/workers/routes"
    existing = api_call("GET", list_path)
    
    # Check if route already exists
    route_exists = False
    if existing.get("success"):
        for r in existing.get("result", []):
            if "healthy-recipes-site.pages.dev" in r.get("pattern", ""):
                route_exists = True
                print(f"  Route already exists: {r.get('pattern')}")
                return True
    
    # Add new route
    body = {
        "pattern": "healthy-recipes-site.pages.dev/*",
        "script": WORKER_NAME
    }
    result = api_call("POST", list_path, body=body)
    if result.get("success"):
        print(f"  ✓ Route added: healthy-recipes-site.pages.dev/*")
        return True
    else:
        print(f"  ✗ Failed to add route: {result.get('errors', result)}")
        return False

def verify_redirect():
    """Step 3: Verify the worker is serving redirects."""
    print("\n=== Step 3: Verify redirect (wait 15s for propagation) ===")
    time.sleep(15)
    
    test_url = "https://healthy-recipes-site.pages.dev/2026/09/12/mediterranean-shrimp-pasta-with-white-wine/"
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        req = urllib.request.Request(test_url, method="GET")
        with opener.open(req, timeout=15) as resp:
            status = resp.status
            location = resp.headers.get("Location", "(none)")
    except urllib.error.HTTPError as e:
        status = e.code
        location = e.headers.get("Location", "(none)")
    
    print(f"  Test URL: {test_url}")
    print(f"  Status: {status}")
    print(f"  Location: {location}")
    
    if status == 301 and TARGET_DOMAIN in location:
        print(f"  ✓ Cross-domain redirect working!")
        return True
    else:
        print(f"  ⚠ Status/location not as expected. May need more time to propagate.")
        return False

def main():
    print("=" * 60)
    print("W82: Deploy Cloudflare Worker for cross-domain redirect")
    print(f"  Old: healthy-recipes-site.pages.dev")
    print(f"  New: {TARGET_DOMAIN}")
    print("=" * 60)
    print()
    
    if not deploy_worker_script():
        sys.exit(1)
    
    if not find_or_create_route():
        sys.exit(1)
    
    verify_redirect()
    
    print("\n" + "=" * 60)
    print("=== Done! ===")
    print("=" * 60)
    print()
    print("老闆 can verify in CF Dashboard:")
    print(f"  https://dash.cloudflare.com/?to=/:account/workers/services/view/{WORKER_NAME}/production")
    print()
    print("老闆's Pages custom domain setup:")
    print("  healthy-recipes-site.pages.dev should NOT need to be a Pages custom domain")
    print("  because the Worker route intercepts traffic BEFORE it hits Pages.")

if __name__ == "__main__":
    main()
