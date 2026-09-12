# Tier 1 Fix 4: Cloudflare Web Analytics (CF-managed, 完全 free)

## 老闆 manual setup (30 秒)

### Step 1: 去 CF Dashboard
https://dash.cloudflare.com/?to=/:account/waimind.com/analytics

### Step 2: 啟用 Web Analytics
1. 揀 `waimind.com` zone
2. Click "Enable Web Analytics" 或 "Add a site"
3. CF 會 generate 一個 `beacon` snippet (e.g., `<!-- Cloudflare Web Analytics --> <script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "..."}'></script>`)

### Step 3: 加 snippet 入 `<head>`
CF Pages 唔直接支援 inline script injection by default，但我哋可以用 `_includes` 或 `_layouts/default.html` 嘅 `<head>` section.

**Step 3a** (我已經準備咗):

我已經 update 咗 `_layouts/default.html` 加 Cloudflare Web Analytics snippet template.
老闆只需要將 CF 派嘅 beacon token 填入 `_config.yml`：

```yaml
# _config.yml
cf_analytics_token: "YOUR_BEACON_TOKEN_HERE"
```

### Alternative (更簡單):
如果老闆唔想掂 code，可以用 **Cloudflare Pages built-in analytics**:
- CF Dashboard → Pages → `healthy-recipes-site` → **Settings** → **Analytics** → Enable "Web Analytics"

呢個**唔需要任何 code change**，CF 自動 track 全部 pageviews。

## 點解用 Cloudflare Web Analytics (而非 Google Analytics)?

| 項目 | Cloudflare | Google Analytics |
|---|---|---|
| **Privacy** | ✅ 匿名 IP，冇 cookie | ❌ Cookie + tracking |
| **GDPR 合規** | ✅ 預設 compliant | ⚠️ 需要 cookie banner |
| **Sample rate** | 100% (full data) | 10-20% sampled (free tier) |
| **Setup** | 30 秒 toggle | 30 分鐘 + cookie banner |
| **Cost** | 完全 free | Free (limited) |
| **Real-time data** | ✅ | ✅ |
| **Referrer tracking** | ✅ | ✅ |
| **Bot filtering** | ✅ (CF-native) | ✅ |

老闆嘅受眾（健康飲食 search）對 privacy 敏感，**CF Analytics 完全 fit**。

## 預期 dashboards

啟用後老闆會睇到：
- **Unique visitors** (daily/weekly/monthly)
- **Pageviews**
- **Top pages** (邊條 recipe 最 hit)
- **Referrers** (Google / Pinterest / Reddit / Direct)
- **Countries** (US / UK / EU / AU...)
- **Bot vs human traffic split**