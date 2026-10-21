# CF Page Rules — W82 Migration Cross-Domain Redirect

## 老闆手動做 (CF Dashboard, 5 min)

### Step 1: 開 CF Dashboard → Pages → healthy-recipes-site
https://dash.cloudflare.com/?to=/:account/pages/view/healthy-recipes-site

### Step 2: 點 "Custom domains" tab → 揀 "Manage" → "Rules" section
或者: 直接去:
https://dash.cloudflare.com/?to=/:account/pages/view/healthy-recipes-site/domains

### Step 3: Create Rule 1 — 老 subdomain → waimind.com
- **Rule name**: `W82: Old subdomain → waimind.com (full redirect)`
- **If URL matches**: 
  - Hostname = `healthy-recipes-site.pages.dev`
  - OR Path starts with: `/`
  - (use: `*healthy-recipes-site.pages.dev/*`)
- **Then**: `Static Redirect`
  - Type: `301 - Permanent Redirect`
  - URL: `https://waimind.com/${uri}` (with path)
  - Expression: `concat("https://waimind.com", http.request.uri.path)`

### Step 4: Create Rule 2 — HTTPS-only + Canonical (optional, security)
- **Rule name**: `W82: Force HTTPS`
- **If URL matches**: `*waimind.com/*`
- **Then**: `Always Use HTTPS`

### Step 5: 老闆嘅 git commit 仍要 `_redirects` intra-site redirects
但 cross-domain 改用 CF Page Rules (Method A)

---

## 老闆 Command line 方案 (alternative)

如果老闆裝咗 `wrangler` CLI，可以用以下 command:

```bash
# Install wrangler
npm install -g wrangler
wrangler login

# List existing rules
wrangler pages rules list --project-name=healthy-recipes-site

# Add cross-domain redirect rule
wrangler pages rules create --project-name=healthy-recipes-site \
  --name="W82: Old subdomain → waimind.com" \
  --expression='(http.host eq "healthy-recipes-site.pages.dev")' \
  --action='redirect' \
  --status=301 \
  --target='concat("https://waimind.com", http.request.uri.path)'
```

---

## Expected Result After Apply

```bash
# Test 1: 老 recipe URL
curl -IL https://healthy-recipes-site.pages.dev/2026/09/12/mediterranean-shrimp-pasta-with-white-wine/
# Expected:
#   HTTP/2 301
#   location: https://waimind.com/2026/09/12/mediterranean-shrimp-pasta-with-white-wine/

# Test 2: 老 root
curl -IL https://healthy-recipes-site.pages.dev/
# Expected:
#   HTTP/2 301
#   location: https://waimind.com/

# Test 3: 老 flat URL (intra-site redirect 仍 work)
curl -IL https://healthy-recipes-site.pages.dev/2026-08-27-one-pot-parmesan-chicken-white-beans/
# Expected:
#   HTTP/2 301
#   location: /2026/08/27/one-pot-parmesan-chicken-white-beans/
#   (then 301 again to https://waimind.com/2026/08/27/one-pot-parmesan-chicken-white-beans/)
```

---

## 老闆 Result Should Be

After this fix:
- ✅ `waimind.com` — primary, serves new build
- ✅ `https://waimind.com/...` — Google indexed, SEO transferred
- ✅ `healthy-recipes-site.pages.dev` → 301 → waimind.com (cross-domain via Page Rule)
- ✅ Intra-site (old flat → date-hierarchy) → 301 → handled by _redirects
- ✅ Total user experience: 老 bookmark 自動去新 domain，零 404

老闆要 +5 分鐘做呢個 step？
