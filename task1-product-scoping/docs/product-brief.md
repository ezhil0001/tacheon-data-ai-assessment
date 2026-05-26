# Product Brief — Marketing Intelligence Digest

---

## Problem

The team answers the same cross-channel performance question multiple times a week.
Today that process is manual, inconsistent, and dependent on one person. This brief
defines the smallest tool that makes that process reliable — without rebuilding how
the team works.

---

## Primary user

Internal analysts and account managers at Tacheon.

Not clients. The client-facing surface comes after the internal workflow is stable
and the team trusts the outputs.

---

## The one thing this tool does

Delivers a consistent, automated cross-channel performance digest every morning
before the team starts work — without someone having to manually pull and summarise
data every morning.

---

## Data sources — V1

| Channel | What we pull | Notes |
|---|---|---|
| Google Ads | Spend, impressions, clicks, conversions, CPA | Via Google Ads API |
| Meta Ads | Spend, reach, conversions, CPA, CTR | Via Meta Graph API |
| GA4 | Sessions, goal completions, bounce rate | Organic traffic only |
| HubSpot | New leads, MQL rate, pipeline value | CRM pipeline signals |

All fetches run in parallel at 08:00 IST daily.
Each channel has an isolated adapter — one failing doesn't block others.

---

## What the user sees

**Summary bar** — total spend, total conversions, blended CPA with week-over-week
delta. Answers the standing question in under 10 seconds.

**Channel cards** — per-channel breakdown with the 3 metrics that matter most for
that channel and their WoW movement.

**Anomaly strip** — appears only when something moves more than ±30% WoW. States
what moved and by how much. Does not suggest action.

**Freshness indicators** — every metric shows when it was last fetched. If a channel
fetch failed or was delayed, it's visible inline — not buried in a log.

**Run log** — last 3 scheduled runs at the bottom of the view. Channels attempted,
rows written, anomalies flagged. Makes data provenance visible without a terminal.

---

## What a successful interaction looks like

An analyst opens Slack at 9am. The digest is already there. They read the summary
bar, check whether anything is flagged, and understand what changed across channels
before their first meeting — without opening a single external tool.

A team lead gets an unexpected client call asking about this week's performance.
They open the internal web view, select the client, read the summary bar, and
answer the question in real time.

That's the scope V1 is designed to solve.

---

## Explicit exclusions

| Feature | Why excluded |
|---|---|
| Client-facing portal | Requires auth, branding, sensitivity controls — separate problem |
| LLM-generated insights | Trust in data has to come before trust in AI interpretation |
| Custom date ranges | Reintroduces the inconsistency this tool is trying to fix |
| Trend charts | Need 4–6 weeks of clean data before they mean anything |
| Budget recommendations | Requires strategy context the tool doesn't have |
| Attribution modelling | Needs team consensus on methodology before it's useful |
| Email delivery | Slack covers the use case; two surfaces create notification noise |

---

## Delivery

| Surface | When | Who |
|---|---|---|
| Slack digest | 08:00 IST daily | Internal team channel |
| Internal web view | On-demand | Analysts and team leads |
| Alert webhook | Triggered by anomaly flag | Same Slack channel |

---

## Storage approach

Append-only. Every scheduled run writes new rows — nothing is updated in place.
This preserves a full historical record of what the system showed at any point in
time. Useful for debugging, useful when a client disputes a number.

Schema per row: `client_id`, `channel`, `metric`, `value`, `period_start`,
`period_end`, `fetched_at`, `run_id`

---

## Anomaly detection — V1

Rule-based threshold: ±30% movement week-over-week triggers a flag.

This is intentionally simple. It works from day one without a historical baseline,
and the logic is fully explainable — the analyst can see exactly why a flag fired.
Threshold will be calibrated per metric after the first 4 weeks of live data.

Statistical or ML-based detection only makes sense once there's enough clean history
to train against. That's a V2 consideration.

---

## AI layer — not in V1

The LLM narrative layer is scoped to V2, after 4–6 weeks of verified data.

When it ships, it will take the structured digest as input and produce a 3-sentence
summary that cites specific numbers from the data. The AI layer should only
summarise structured data that already exists in storage.

Reason for the delay: one AI-generated insight that contradicts what an analyst
manually verified will damage trust in the entire system, including the correct
structured data underneath. The data trust layer comes first.

---

## Why Slack-first

The team already works inside Slack throughout the day. Delivering the digest there
reduces adoption friction because the workflow doesn't change — the information just
arrives earlier and in a more consistent format.

The internal web view exists for drill-down and historical lookup, not as the
primary entry point.

---

## Open questions

These are things I'd need to resolve before V1 ships:

1. Which Slack channel does the digest go to — one shared channel or per-client
   channels?
2. Is the internal web view behind any access control, or is it open on the
   internal network?
3. Who owns the API credentials for each client — the client or Tacheon?
4. Is ±30% the right starting threshold, or does the team have a sense of normal
   variance from their existing manual process?
5. What's the handover plan — how long does manual reporting run in parallel before
   V1 takes over fully?

---

## What this is not

This is not a BI tool. It doesn't replace Google Looker Studio or Meta's native
reporting. It doesn't let users explore data freely or build custom views.

It answers one recurring operational question, consistently, every day, without
anyone having to ask.

That's the scope. Everything else is a later version.