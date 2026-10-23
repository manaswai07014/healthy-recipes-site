# Reddit Playbook — waimind.com

**Created**: 2026-10-23 (W98)
**Baseline that motivated this**: waimind.com = 7 pageviews / 7 days (~1/day). No discovery channel is running. Reddit is the lowest-credential community channel available, but it only works as *participation*, never as link-dropping.

All subreddit observations below come from live reads via the `reddit-reading` skill
(anonymous Atom backend) on 2026-10-23. Nothing here is assumed.

---

## 1. Target subreddits (probed, real)

### r/mediterraneandiet — PRIMARY
- **Why**: exact niche match (Mediterranean diet eaters actively asking recipe questions).
- **Observed culture (2026-10-23 hot listing)**: people post photos of their own meals
  with a short ingredient write-up ("Multigrain bread, grilled with extra virgin olive oil…
  crunchy Mediterranean salad over a bed of sardine dip…"), plus genuine questions
  ("What healthy sauce goes with cod and potatoes?", "Looking for a good crusty roll/baguette").
- **Entry angle that fits the culture**: answer the *question* posts with a real, specific
  answer. Do not paste a link as the answer.

### r/EatCheapAndHealthy — SECONDARY
- **Why**: high recipe-request volume; also hosts brand AMAs (Budget Bytes ran one).
- **Observed culture**: direct recipe requests ("Tell me your fav crockpot meals"),
  practical constraints (economy, time), snack questions. Skeptical of marketing.
- **Caveat**: our recipes are low-calorie/high-protein, not budget-first — lead with the
  *practical* framing (cheap + fast + filling), not with the calorie claim.

### r/HealthyFood — CAUTION
- **Observed rule (from the sub's own AutoModerator post)**: *"All posts MUST go through an
  approval process involving moderator review… There is an extremely high percentage of
  attempted participation in this sub coming from spammers and scammers."*
- **Implication**: a low-karma account dropping recipe links will simply never be approved.
  Treat this sub as read-only until the account has real history elsewhere.

---

## 2. Account prerequisites (do these BEFORE any post)

Reddit bans link-droppers, not brands. The account must look like a person first.

1. Create a normal account; do **not** name it after the site.
2. 2 weeks of pure participation: comment answers on r/mediterraneandiet question posts,
   no links at all.
3. Only after that, and only where a link genuinely answers the question, include one link.
4. Keep a ratio of roughly **10 comments : 1 link**. Any ratio where links dominate is a
   ban risk.

---

## 3. Post/comment templates (culture-matched)

### A. Answer a question post (the main play)
Question observed: *"What healthy sauce goes with cod and potatoes?"*

> Greek yogurt with lemon, garlic and dill — thin it with a little olive oil and it works
> on both the fish and the potatoes. If you want something warmer, a tomato-caper sauce
> also goes well with cod. Both keep the fat low without tasting like diet food.

**Rules**: answer in the comment. Link only if the user asks for the recipe, then link the
single most relevant page. Never link in the first comment.

### B. Photo post (r/mediterraneandiet's native format)
Post the dish photo + an honest ingredient/technique write-up in the same voice as the
community (they write plainly: what they cooked, how, what they'd change). A link goes in
the body *only* if the sub's rules and the post's framing make it natural, and never as the
first thing.

### C. AMA / brand introduction (only after 1–2 months of history)
Triggered by seeing established brands do it (Budget Bytes). Not a first-month move.

---

## 4. Cadence (name it, or it won't happen)

| Week | Action |
|---|---|
| 1–2 | 5 comments/week on r/mediterraneandiet question posts. Zero links. |
| 3–4 | 5 comments/week + 1 photo post. One link allowed, only if asked. |
| 5+ | Maintain 5 comments/week + 1–2 photo posts. Review what got engagement. |

**Budget**: ~20 minutes/day. This is a slow channel — it compounds, it does not spike.

---

## 5. Risk register

| Risk | Mitigation |
|---|---|
| Permanent ban for self-promotion | 10:1 comment:link ratio; never link-first |
| r/HealthyFood auto-reject | Don't post there until the account has real history |
| Account-aging requirement | Start the account now even if posting starts later |
| Time sink with no traction | Cap at 20 min/day; review at week 6 and stop if no signal |

---

## 6. How to read results (honest measurement)

- Reddit rarely shows up as much traffic per post; it shows up as **a few qualified visits**
  and, more importantly, as **brand searches** later.
- Track in Cloudflare Web Analytics: look for `/` and recipe-page visits with a
  `reddit.com` referrer. Current baseline is 7 pageviews/week, so even 10 visits from a
  single thread is a visible signal.
- Do **not** judge this channel by pageview count in month 1. Judge it by whether comments
  get upvotes / replies — that is whether the account is accepted.

---

## 7. Non-goals

- No link-dropping in unrelated subs.
- No vote manipulation / alt accounts.
- No posting the same text across subs (site-wide spam signal).
- No buying upvotes or accounts.
