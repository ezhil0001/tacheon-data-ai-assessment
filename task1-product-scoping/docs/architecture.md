# Architecture — Marketing Intelligence Digest

This document covers the system's component structure — what each layer is
responsible for, where the boundaries are, and the reasoning behind key design
decisions.

---

## System overview

The system is split into five layers. Each layer has a clearly defined
responsibility and communicates with adjacent layers through a fixed interface.
Each layer exposes a narrow interface so changes stay isolated as much as possible.

```text
┌─────────────────────────────────────────────┐
│              External APIs                  │
│   Google Ads · Meta Graph · GA4 · HubSpot   │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│            Connector Layer                  │
│   One adapter per platform. Handles auth,   │
│   retries, rate limits, error isolation,    │
│   and schema normalisation.                 │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│            Processing Layer                 │
│   Delta calculation · Anomaly detection     │
│   Freshness tagging · Client scoping        │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│             Storage Layer                   │
│   Append-only time-series · Run log         │
│   Anomaly events · Digest cache             │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│            Delivery Layer                   │
│   Slack digest · Internal web view          │
│   Alert webhook                             │
└─────────────────────────────────────────────┘
```

Running alongside all five layers:

```text
┌─────────────────────────────────────────────┐
│            Orchestration Layer              │
│   Scheduler · Retry logic · Run state       │
│   Structured logging · Alert dispatch       │
└─────────────────────────────────────────────┘
```

---

## Connector layer

**What it owns**

Each platform has its own adapter file. The adapter handles everything specific
to that platform: OAuth token management, pagination, rate limit handling, retry
on transient failures, and mapping the raw API response to the canonical MetricRow
schema.

The adapter exposes one function to the rest of the system:

```text
fetch(client_id, date_range) → List[MetricRow]
```

Everything downstream works against that interface rather than platform-specific
logic.

**What it doesn't own**

The connector layer has no knowledge of deltas, anomalies, or storage. It fetches
and normalises. Nothing else.

**Why one adapter per platform**

Platform APIs change — deprecations, version updates, field renames. Isolating each
platform means a breaking change in the Meta Graph API doesn't affect the Google
Ads adapter or anything downstream. The canonical schema stays stable even as
upstream APIs shift.

Adding a new channel means adding one adapter file. Processing, storage, and delivery layers remain unchanged.

---

## Processing layer

**What it owns**

Three operations, run in sequence after every successful fetch:

**Delta calculation** — compares the current 7-day window against the prior 7-day
window for each metric. Produces absolute change and percentage change. Queries
storage for prior period values.

**Anomaly detection** — checks each delta against the configured threshold. Defaults
to ±30% week-over-week. Produces a list of flagged metrics with their movement
values. Threshold is configurable per metric in the config layer.

**Freshness tagging** — stamps each MetricRow with the fetch timestamp and whether
the source fetch was partial or delayed. This is what drives the staleness
indicators in the UI.

**What it doesn't own**

The processing layer doesn't know about delivery surfaces. It produces a structured
digest payload. What happens to that payload is the delivery layer's concern.

It also doesn't query external APIs directly. It only works with MetricRow objects
that the connector layer produced.

**Why pure functions here**

Each operation in the processing layer is written so that given the same input data,
the output should always be deterministic. This makes them independently testable
with synthetic data before any real API connection exists. Delta logic and anomaly
logic can be validated completely in isolation.

---

## Storage layer

**What it owns**

Two primary tables:

**metric_snapshots** — the main data store. Append-only. One row per metric per
channel per client per run. Never updated in place. Every row carries a run_id
that links it back to the run that produced it.

**run_log** — one entry per scheduled run. Tracks which channels were attempted,
which succeeded, row counts, anomaly counts, timing, and error messages if any.
This is the source of truth for the run log panel in the UI.

Two supporting structures:

**anomaly_events** — a filtered view of flagged metrics from each run. Keeps
anomaly history queryable without scanning the full metric_snapshots table.

**digest_cache** — the processed digest payload stored after each successful run.
The delivery layer reads from here rather than reprocessing on every request.

**What it doesn't own**

Storage doesn't decide what gets fetched or how it gets delivered. It receives
structured data and returns structured data. Schema migrations and data retention
policies live here but nowhere else.

---

## Delivery layer

**What it owns**

Three surfaces, all reading from the same digest cache:

**Slack digest** — formatted message posted to the configured internal channel at
08:00 IST. Includes summary bar, channel breakdown, and anomaly flags if present.
Slack delivery happens once per scheduled run, so additional caching isn't
necessary there.

**Internal web view** — lightweight read-only UI. Reads from digest cache. Supports
manual refresh (rate-limited to avoid API hammering). Client selector in topbar.
Run log panel at the bottom.

**Alert webhook** — fires to Slack when anomaly events are present in the run.
Separate from the digest message so anomaly alerts are distinguishable in the
channel. Same Slack channel, different message format.

**What it doesn't own**

The delivery layer doesn't process or transform data. It formats and sends. If the
digest cache is empty or stale, it surfaces that state rather than fetching
anything itself.

---

## Orchestration layer

**What it owns**

The orchestration layer runs alongside everything else. It's not a separate service
— in V1 it's a scheduled job that coordinates the other layers.

**Scheduler** — triggers the fetch cycle at 08:00 IST. In V1 this is a simple cron
job or cloud scheduler task. In V2 this becomes a proper workflow with step-level
retry and observability.

**Retry logic** — if a fetch fails with a transient error (timeout, 5xx), the
adapter retries up to 3 times with exponential backoff before marking the channel
as failed for that run. The orchestrator tracks retry attempts per channel per run.

**Run state tracking** — maintains the current run's state so partial failures are
recorded accurately. If the process crashes mid-run, the run is marked incomplete
rather than silently missing from the log.

**Structured logging** — every operation logs a JSON entry with run_id, timestamp,
level, and message. This means any run can be fully reconstructed from logs using
just its run_id.

---

## Extensibility

A few things were designed specifically to make future changes low-cost:

**New channel** — one new adapter file. Connector, processing, storage, and
delivery are untouched.

**New client** — add credentials to secrets store, add a row to the client config.
No code change.

**New delivery surface** — add one new formatter that reads from digest cache.
Processing and storage are untouched.

**Swap anomaly detection logic** — the anomaly detector is an isolated function
with a fixed interface. Replace the threshold logic with a statistical model when
enough historical data exists. Nothing downstream changes.

**AI narrative layer (V2)** — sits entirely downstream of storage. Reads the
structured digest payload, generates a summary, appends it to the digest cache.
Can be deployed, disabled, or rolled back independently of everything else.

---

## What this architecture is not trying to do

It's not trying to be a general-purpose data platform. The schema, the adapters,
and the delivery surfaces are all specific to answering one recurring operational
question for one team. That specificity is intentional — it's what keeps V1
small enough to ship and trust quickly.

Generalising it — making adapters pluggable via config, building a query interface,
supporting arbitrary metric definitions — only makes sense once the team is
consistently relying on the workflow day to day.