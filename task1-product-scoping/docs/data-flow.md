# Data Flow — Marketing Intelligence Digest

This document covers how data moves through the system during a scheduled run.
Not every edge case — just the main path and the two failure scenarios worth
understanding upfront.

---

## Scheduled run — main path

```text
08:00 IST — Scheduler fires
        │
        ▼
Fetch layer — parallel per channel
  ┌─────────────┬──────────────┬─────────┬──────────┐
  │ Google Ads  │   Meta Ads   │   GA4   │ HubSpot  │
  └─────────────┴──────────────┴─────────┴──────────┘
        │
        ▼
Result check — per channel
  ┌─────────────────────────────────────────────┐
  │ Success → normalise to canonical schema     │
  │ Failure → mark channel stale, continue run  │
  └─────────────────────────────────────────────┘
        │
        ▼
Processing layer
  1. Normalise  — flatten each response to MetricRow schema
  2. Delta      — calculate WoW change vs prior 7-day window
  3. Anomaly    — flag if movement exceeds ±30% threshold
  4. Freshness  — stamp each row with fetched_at + run_id
        │
        ▼
Storage — append-only write
  New rows inserted for this run.
  Nothing from previous runs is touched.
        │
        ▼
Delivery — parallel
  ┌──────────────────┬─────────────────────┬────────────────┐
  │  Slack digest    │  Web view refresh   │  Alert webhook │
  │  (always fires)  │  (cache invalidate) │  (if flagged)  │
  └──────────────────┴─────────────────────┴────────────────┘
        │
        ▼
Run log entry written
  run_id · started_at · completed_at · channels_ok · channels_failed
  rows_written · anomalies_flagged · status
```

---

## Failure scenario 1 — one channel is down

If a single channel fetch fails (API timeout, 503, token expiry), the run
continues with the remaining channels. The failed channel is marked stale in
storage and the digest is delivered with a visible warning on that channel card.

The run log records the failure with the error reason. An alert fires to Slack
noting which channel was unavailable.

The analyst sees a partial digest with clear staleness indicators — not a
complete-looking digest with silently wrong data.

This matters because silent failures are worse than visible ones. If Meta numbers
are missing and the analyst doesn't know, they might make a call based on incomplete
cross-channel totals. The staleness flag prevents that.

---

## Failure scenario 2 — full run fails

If the scheduler fires but the run crashes before delivering anything, no digest
is posted to Slack that morning.

If the digest doesn't arrive by the usual time, the team notices quickly because
it's part of the daily workflow already. The run log records the failure with the
error reason for debugging.

In V2 this gets an explicit dead-letter alert — "today's digest did not complete"
posted to Slack automatically. In early versions, the missing digest itself is
enough to signal that something failed in the pipeline.

---

## Canonical schema

Every adapter outputs the same structure regardless of source platform.
The processing layer never sees raw API responses — only normalised rows.
This means adding a new channel is writing one new adapter; nothing downstream
changes.

| Field | Purpose |
|---|---|
| run_id | Unique identifier for the scheduled run |
| client_id | Client workspace identifier |
| channel | Source platform — google_ads, meta, ga4, hubspot |
| metric | Metric name — spend, conversions, cpa, etc. |
| value | Metric value for the period |
| period_start | Start of the reporting window |
| period_end | End of the reporting window |
| fetched_at | Timestamp of when the fetch completed |
| is_stale | Whether the fetch was partial or delayed |

---

## Caching

Caching exists to reduce unnecessary API calls, not to optimise frontend latency.

Two places where it makes sense:

**Fetch cache (15 min TTL)** — the internal web view can be refreshed manually.
Without caching, every manual refresh hits external APIs and burns rate limit quota.
Raw fetch result cached per `client_id + channel + date_range`. Invalidated on
next successful scheduled run.

**Digest cache (1 hour TTL)** — the processed digest payload is deterministic
given the same fetch result. The delivery layer reads from this cache rather than
reprocessing every time someone opens the web view.

Slack delivery doesn't need additional caching because messages are only sent once
per scheduled run.

---

## What triggers an anomaly alert

The anomaly check runs after deltas are calculated. Current logic:

```text
if abs(wow_delta_pct) >= 0.30:
    flag as anomaly
    record in anomaly_events
    trigger alert webhook
```

Threshold defaults to 30% across all metrics in V1. After 4 weeks of live data,
this gets reviewed per metric per client based on observed normal variance.

The alert fires to the same Slack channel as the digest — The alert goes to the same Slack channel as the digest so the workflow stays in
one place.

---

## Storage write pattern

Every run writes to two tables:

**metric_snapshots** — one row per metric per channel per client. Main data table.
Never updated, only appended.

**run_log** — one row per scheduled run. Records timing, channel status, row counts,
and any errors. This is what the UI run log panel reads from.

Both tables are written as part of the same run process so operational status and
metric data stay aligned.

---

## Why append-only

Updating rows in place would be simpler in some ways. The reason it's not done:

If a fetch returns slightly different numbers on a retry — which happens occasionally because APIs can have eventual consistency quirks — updating in place silently changes historical data.
With append-only, both versions exist and the run_id tells you which fetch produced
which number. That's the audit trail.

It also means V2 trend charts have a complete dataset to draw from without any
migration. The data has been accumulating correctly from day one.

