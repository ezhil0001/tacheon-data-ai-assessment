# Task 1 — Product Scoping

## The problem

Marketing teams at multi-client agencies answer the same question constantly:

> "How is our marketing performing across channels right now, and where should we focus?"

Today that answer lives in someone's head. Getting it out requires opening 4–5 tools,
pulling numbers manually, pasting them somewhere, and writing a summary. The answer
looks different every time depending on who does it. If that person is busy, the
question just sits there.

This isn't a data problem. The data exists. It's a knowledge distribution problem.

Three things break as a result:

- **Inconsistency** — no standard format, no standard metrics, no standard time window
- **Dependency** — one person holds the process; when they're unavailable, nothing moves
- **No audit trail** — no reliable historical snapshot of what was reported at a specific point in time

---

## Who this is for

V1 is designed for internal analysts and team leads only.

Not clients. That's a deliberate call.

The pain described is entirely internal. Building a client-facing tool in V1 means
adding auth, data sensitivity controls, branding, and a higher trust standard —
none of which address the actual problem. A client-facing version makes more sense
after the internal workflow stabilizes and the team has confidence in the consistency
of the outputs.

---

## Why this format

The team already has dashboards inside each individual platform. The gap is not
visualisation — it's operational consistency.

The value of this tool is reducing the time and variability involved in answering
the same recurring cross-channel question every day.

V1 optimizes for operational visibility, not strategic decision automation.

---

## What V1 does

The goal in V1 is to answer a single recurring operational question consistently,
without expanding scope into reporting or client communication workflows yet.

**Scheduled fetch** — every morning at 8am, the system pulls the last 7 days of
performance data from connected channels: Google Ads, Meta Ads, GA4, HubSpot.
Parallel fetches, one adapter per platform.

**Summary bar** — three numbers at the top: total spend, total conversions, blended
CPA — each with a week-over-week delta. A team lead can answer the standing question
in under 10 seconds without reading anything else.

**Channel breakdown** — per-channel cards with the metrics that matter for that
channel. Spend, CPA, conversions for paid. Sessions, bounce, goal completions for
GA4. Lead count, MQL rate, pipeline value for HubSpot.

**Freshness indicators** — every metric shows when it was last successfully fetched.
If a fetch fails, the channel is marked stale. No silent failures.

**Anomaly flags** — if any metric moves more than ±30% week-over-week, it surfaces
at the top of the digest and inline on the channel card. The flag states what moved.
Not why. Not what to do. That's intentional.

**Run log** — last 3 scheduled runs visible in the UI: which channels succeeded,
how many rows written, whether anything was flagged. Makes the tool debuggable
without opening a terminal.

**Per-client scoping** — supports multiple client workspaces from day one. Client selector in the topbar.
Data isolated per client. Not client-facing; just internal data organisation.

---

## What V1 does not do

These were considered and cut. The reasoning matters more than the list.

**No client portal** — requires auth, sensitivity review, branding. Doubles scope
without solving the core pain. A client-facing surface only makes sense once the
internal layer is stable and trusted.

**No LLM narrative** — if the underlying numbers are questioned, an AI-generated
explanation won't help. The reporting layer needs to become trustworthy before
adding generated insights.

**No custom date ranges** — arbitrary windows reintroduce inconsistency. V1 enforces
canonical 7-day windows so everyone is looking at the same thing.

**No trend charts** — meaningless with less than 4–6 weeks of clean data. Storage
is append-only from day one so the data accumulates. Charts get added when they
become truthful.

**No recommendations** — "pause Meta, shift budget to Google" requires strategy
context the tool doesn't have. The tool shows what changed. The analyst decides
what to do.

**No attribution modelling** — generates more disagreement than clarity until the
team agrees on methodology.

---

## Architecture

The system is intentionally split into separate layers so connectors, processing
logic, and delivery channels can evolve independently without rewriting the whole
workflow.

External APIs
Google Ads · Meta Graph · GA4 · HubSpot
↓
Connector layer
One adapter per platform — auth, retries, rate limits, schema normalisation
↓
Processing layer
Delta calculator · Anomaly detector (threshold-based) · Freshness tagger
↓
Storage layer
Append-only time-series — never overwrite, every row tagged with run_id + fetched_at
↓
Delivery layer
Slack digest (08:00 scheduled) · Internal web view · Alert webhook

Data is stored append-only rather than updated in place. That keeps a historical
record of what the system showed at a specific point in time — useful the first
time a client disputes a number or the team needs to understand what changed
between two runs.

Anomaly detection is rule-based in V1. ±30% week-over-week threshold. Fully
explainable, works from day one, no historical baseline required. The threshold
is configurable per metric once real variance data accumulates.

---

## Tradeoffs

**Consistency over flexibility** — fixed metrics, fixed windows, fixed cadence.
This reduces flexibility early on, but the inconsistency problem already comes from
different people pulling different windows and metrics every time. A shared frame
of reference has to come before optionality.

**Reliability over intelligence** — no LLM in V1. One wrong AI output early on
damages trust in the whole system. Structured, verifiable data first. Generated
insights only after the data layer has been validated.

**Transparent failure over silent failure** — partial digest with visible staleness
indicators beats a complete-looking digest that's silently wrong. Users should
always know the provenance of what they're looking at.

---

## Assumptions

- API credentials exist or can be obtained for each client's platforms
- The team uses Slack as primary internal communication
- ±30% threshold is a starting point; needs calibration after first 4 weeks of
  live data
- Platform set is stable for the V1 lifetime per the brief's constraint

---

## Risks

**Adoption** — the analyst doesn't trust V1 outputs initially and keeps running
manual reports in parallel. Mitigation: run both for 2 weeks, document every
discrepancy, agree on a named handover date.

**Alert fatigue** — if anomaly flags fire every morning, people stop reading them.
Threshold needs per-metric calibration based on observed variance, not a flat
default forever.

**API deprecation** — Google Ads and Meta both version their APIs on announced
timelines. Isolating each platform in its own adapter means one breaking change
doesn't affect the others.

---

## Roadmap

| Version | Scope |
|---|---|
| V1 | Automated digest, WoW deltas, rule-based anomaly flags, freshness indicators, run log, Slack + internal web view |
| V2 | LLM narrative layer (cited numbers only), trend charts, 28-day rolling baseline, budget pacing alerts, custom date ranges |
| V3 | Client-facing read-only view, internal chat interface, attribution modelling, portfolio health view |
| V4 | Predictive budget suggestions, automated client report generation, competitive benchmarking |

---

## What I'd revisit with more time

The anomaly threshold is a starting assumption. With 6 months of the team's
historical data I'd set per-metric thresholds based on actual observed variance
rather than a flat 30%.

The metric set is assumed. In a real engagement I'd spend time watching an analyst
build their manual report before deciding which numbers go in V1. The tool should
reflect how the team actually thinks, not how a spec assumes they think.

Client onboarding is a developer task in V1 — add credentials, update config. That
becomes a bottleneck past 5 clients and needs a self-serve flow before V2 ships.

---

*Data flow and architecture diagrams are in `diagrams/`. Wireframe reference is in
`wireframes/`.*
