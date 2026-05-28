import sys
import uuid
import time
import logging
import os
import pandas as pd

# Logging configured before any module import so all loggers
# inherit the same format and handlers from the start
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/pipeline.log", encoding="utf-8"),
    ],
)

log = logging.getLogger("pipeline")

from pipeline.fetcher     import fetch_all_locations
from pipeline.validator   import validate_api_response, validate_dataframe
from pipeline.transformer import transform
from pipeline.loader      import BigQueryLoader


def run() -> None:
    run_id  = str(uuid.uuid4())
    started = time.time()

    log.info("=" * 60)
    log.info(f"Pipeline started — run_id: {run_id}")
    log.info("=" * 60)

    try:
        # Stage 1 — Fetch
        t0 = time.time()
        log.info("Stage 1/4 — Fetching from Open-Meteo")
        raw_results = fetch_all_locations()
        log.info(
            f"Stage 1 complete — "
            f"locations: {len(raw_results)}, "
            f"duration: {round(time.time()-t0, 2)}s"
        )

        # Stage 2 — Validate and transform per location
        t0 = time.time()
        log.info("Stage 2/4 — Validating and transforming")
        frames = []

        for item in raw_results:
            location = item["location"]
            raw      = item["data"]

            validate_api_response(raw, location["name"])
            df = transform(raw, location, run_id)
            validate_dataframe(df, location["name"])
            frames.append(df)

        if not frames:
            raise RuntimeError(
                "No data survived validation — nothing to load"
            )

        log.info(
            f"Stage 2 complete — duration: {round(time.time()-t0, 2)}s"
        )

        # Stage 3 — Combine all location DataFrames
        t0       = time.time()
        combined = pd.concat(frames, ignore_index=True)

        location_summary = combined.groupby("location").size().to_dict()
        log.info(
            "Stage 3/4 — Combined rows: {} | {}".format(
                len(combined),
                " | ".join(
                    f"{k}: {v}" for k, v in location_summary.items()
                )
            )
        )
        log.info(
            f"Stage 3 complete — duration: {round(time.time()-t0, 2)}s"
        )

        # Stage 4 — Load to BigQuery
        t0 = time.time()
        log.info("Stage 4/4 — Loading to BigQuery")
        loader               = BigQueryLoader()
        rows_written, job_id = loader.setup_and_load(combined)
        log.info(
            f"Stage 4 complete — duration: {round(time.time()-t0, 2)}s"
        )

        duration = round(time.time() - started, 2)
        log.info("=" * 60)
        log.info(
            f"Pipeline complete — "
            f"run_id: {run_id} | "
            f"rows: {rows_written} | "
            f"bq_job: {job_id} | "
            f"duration: {duration}s"
        )
        log.info("=" * 60)

    except Exception as exc:
        duration = round(time.time() - started, 2)
        log.error("=" * 60)
        log.error(
            f"Pipeline failed — "
            f"run_id: {run_id} | "
            f"duration: {duration}s"
        )
        log.error(f"Error: {exc}", exc_info=True)
        log.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    run()