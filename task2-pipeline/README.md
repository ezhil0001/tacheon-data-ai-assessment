# Task 2 — Data Pipeline

A small but complete data pipeline that fetches weather data for five Indian
metros, transforms it into a marketing-relevant format, and loads it to
BigQuery for analysis.

---

## Why this API

Open-Meteo — no API key, no account, no billing setup required.

The marketing narrative: Indian D2C brands run campaigns where performance
is directly affected by weather. Mamaearth's sunscreen campaigns underperform
during monsoon. Zomato's delivery demand spikes above 38°C. boAt's outdoor
campaigns lose reach during heavy rain.

This pipeline gives a marketing team a daily weather risk signal per city —
something they can eventually correlate against campaign performance data to
understand when to push budget and when to pull it back.

---

## Pipeline structure

```
config/settings.py      — environment-driven configuration
pipeline/fetcher.py     — API fetch with retry logic
pipeline/validator.py   — response and dataframe validation
pipeline/transformer.py — flatten, clean, derive campaign_risk_index
pipeline/loader.py      — BigQuery batch load
run_pipeline.py         — entry point, wires all layers
queries/                — analytical SQL queries
tests/                  — unit tests, no external dependencies
```

Each layer has one responsibility. The fetcher doesn't know about BigQuery.
The loader doesn't know about the API. The entry point wires them in sequence.

---

## What the pipeline produces

One row per city per day. Total rows depend on the configured fetch window.

The key derived field is `campaign_risk_index` — a composite score between
0 and 1 built from temperature variance, precipitation probability, and wind
speed. It doesn't exist in the raw API response. It's what the pipeline adds.

| Field | Description |
|---|---|
| fetch_date | Calendar date for the weather reading |
| location | City name |
| avg_temp_c | Average temperature for the day |
| temp_variance_c | Difference between max and min temp |
| precipitation_mm | Total rainfall in mm |
| precipitation_prob | Probability of precipitation (%) |
| windspeed_kmh | Max wind speed |
| campaign_risk_index | Composite risk score 0–1 |
| risk_category | HIGH / MEDIUM / LOW |
| pipeline_run_id | UUID linking rows to a specific run |
| ingested_at | UTC timestamp of when the row was written |

---

## BigQuery note

The loader uses `load_table_from_dataframe` — batch load only.

Streaming inserts (`insert_rows_json`) are blocked in BigQuery Sandbox and
cost more in production. Every decision in the loader is made with Sandbox
compatibility in mind.

The table is partitioned on `fetch_date`. Queries that filter by date only
scan relevant partitions rather than the full table.

---

## Setup

**1. Clone the repo and install dependencies**

```bash
cd task2-pipeline
pip install -r requirements.txt
```

**2. Configure environment**

```bash
cp .env.example .env
```

Open `.env` and fill in your GCP project ID. Everything else has a sensible
default.

**3. GCP authentication**

```bash
gcloud auth application-default login
```

Or set `GOOGLE_APPLICATION_CREDENTIALS` to the path of a service account
key. The pipeline uses whichever credential is available in the environment.

**4. BigQuery Sandbox**

Visit [console.cloud.google.com/bigquery](https://console.cloud.google.com/bigquery).
A default project is created automatically with a Google account. No billing
required.

The pipeline creates the dataset and table on first run if they don't exist.
Nothing needs to be set up manually in BigQuery.

---

## Running the pipeline

```bash
python run_pipeline.py
```

Expected output:

```
2026-05-26 08:14:01 | INFO | pipeline | Pipeline started — run_id: a3f8c2d1-...
2026-05-26 08:14:06 | INFO | pipeline | Stage 1 complete — duration: 5.2s
2026-05-26 08:14:07 | INFO | pipeline | Combined rows: 70 | Mumbai: 14 | Delhi: 14 | Bangalore: 14 | Chennai: 14 | Kolkata: 14
2026-05-26 08:14:09 | INFO | loader   | BQ load complete — rows: 70, job_id: abc123
2026-05-26 08:14:09 | INFO | pipeline | Pipeline complete — rows: 70 | duration: 8.1s
```

If it fails, exit code is 1 and the full error is in `logs/pipeline.log`.

---

## Running tests

```bash
python -m pytest tests/ -v
```

Tests use synthetic data and mocked HTTP responses. No real API calls, no
BigQuery connection required.

---

## SQL queries

See `queries/summary_analysis.sql` for six analytical queries covering
weekly risk summary, city ranking, 14-day trend analysis, heat stress
days, and a pipeline data quality audit.

Replace `your_project` with your actual GCP project ID before running.

**Sample output — Query 2: City risk ranking, current week**

| location | avg_risk_this_week | avg_temp_c | avg_rain_probability_pct | risk_category | risk_rank |
|---|---|---|---|---|---|
| Mumbai | 0.618 | 31.2 | 74.0 | HIGH | 1 |
| Delhi | 0.541 | 38.4 | 52.0 | MEDIUM | 2 |
| Kolkata | 0.489 | 33.1 | 61.0 | MEDIUM | 3 |
| Chennai | 0.401 | 34.8 | 45.0 | MEDIUM | 4 |
| Bangalore | 0.287 | 26.3 | 28.0 | LOW | 5 |

---

## Production notes

**Scheduling**
Cloud Scheduler triggering a Cloud Run Job. The pipeline reads config from
environment variables, logs to stdout, and exits 0 on success and 1 on
failure. It is structured in a way that can be containerised for Cloud Run
deployment later with minimal changes.

**Failure alerting**
Cloud Monitoring alert on non-zero exit code routed to Slack via webhook.
The alert includes the run_id so the engineer can immediately query BigQuery
or grep the logs for that specific execution.

**Scaling**
Two changes matter most when data volume grows:
- Incremental loads using a watermark — fetch only dates not already in
  BigQuery rather than the full window every run
- Load per-location instead of combining into one DataFrame — keeps memory
  usage predictable as more cities are added

**Known limitation**
If the pipeline transforms successfully but the BigQuery load fails, a retry
will re-load the same dates. With `WRITE_APPEND` this creates duplicate rows.
The fix is checking whether today's data already exists before loading — not
built in V1 but the first thing to add before this goes to production.

---

## What I would do differently with more time

The `campaign_risk_index` weights (precipitation 0.50, temp variance 0.30,
wind 0.20) are assumptions. With actual campaign performance data to cross-
reference, these weights could be calibrated per category — a sunscreen brand
cares more about temperature than a food delivery platform does.

Dead letter handling is missing. If a payload passes response validation but
fails DataFrame validation, that raw response is lost. Writing failed payloads
to a staging location would allow reprocessing without re-fetching.