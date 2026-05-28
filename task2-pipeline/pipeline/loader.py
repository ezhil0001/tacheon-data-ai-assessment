import logging
import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPIError, NotFound

from config import settings

log = logging.getLogger(__name__)

# Table schema — matches transformer output exactly.
# weathercode stored as FLOAT64 to avoid pyarrow nullable
# integer serialization issues across library versions.
SCHEMA = [
    bigquery.SchemaField("fetch_date",          "DATE",      "REQUIRED"),
    bigquery.SchemaField("location",            "STRING",    "REQUIRED"),
    bigquery.SchemaField("country",             "STRING",    "REQUIRED"),
    bigquery.SchemaField("latitude",            "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("longitude",           "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("avg_temp_c",          "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("max_temp_c",          "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("min_temp_c",          "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("temp_variance_c",     "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("precipitation_mm",    "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("precipitation_prob",  "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("windspeed_kmh",       "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("weathercode",         "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("campaign_risk_index", "FLOAT64",   "NULLABLE"),
    bigquery.SchemaField("risk_category",       "STRING",    "NULLABLE"),
    bigquery.SchemaField("pipeline_run_id",     "STRING",    "REQUIRED"),
    bigquery.SchemaField("ingested_at",         "TIMESTAMP", "REQUIRED"),
]


class BigQueryLoader:
    """
    Handles all BigQuery operations for the pipeline.

    Uses load_table_from_dataframe exclusively — batch load via
    local parquet serialization and GCS staging.

    Streaming inserts (insert_rows_json) are deliberately not used:
      - blocked in BigQuery Sandbox
      - higher cost per row in production
      - weaker consistency guarantees on large loads

    Table is partitioned on fetch_date so date-filtered queries
    scan only relevant partitions rather than the full table.
    """

    def __init__(self) -> None:
        self.client    = bigquery.Client(project=settings.GCP_PROJECT_ID)
        self.table_ref = (
            f"{settings.GCP_PROJECT_ID}."
            f"{settings.BQ_DATASET}."
            f"{settings.BQ_TABLE}"
        )

    def ensure_dataset_exists(self) -> None:
        dataset_ref = bigquery.DatasetReference(
            settings.GCP_PROJECT_ID,
            settings.BQ_DATASET,
        )
        try:
            self.client.get_dataset(dataset_ref)
            log.info(f"Dataset exists — {settings.BQ_DATASET}")
        except NotFound:
            dataset          = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            self.client.create_dataset(dataset, exists_ok=True)
            log.info(f"Dataset created — {settings.BQ_DATASET}")

    def ensure_table_exists(self) -> None:
        try:
            self.client.get_table(self.table_ref)
            log.info(f"Table exists — {self.table_ref}")
        except NotFound:
            table = bigquery.Table(self.table_ref, schema=SCHEMA)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="fetch_date",
            )
            table.description = (
                "Daily weather data for Indian metros with derived "
                "campaign_risk_index. Partitioned by fetch_date. "
                "Append-only — rows are never updated in place."
            )
            self.client.create_table(table, exists_ok=True)
            log.info(f"Table created — {self.table_ref}")

    def load(self, df: pd.DataFrame) -> tuple:
        """
        Batch loads DataFrame to BigQuery.

        WRITE_APPEND — each run adds new rows, nothing is
        overwritten. Keeps a full history of every pipeline run.

        Returns (rows_written, job_id) for observability.
        """
        job_config = bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            time_partitioning=bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="fetch_date",
            ),
            create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
        )

        log.info(
            f"Starting BQ load — "
            f"rows: {len(df)}, table: {self.table_ref}"
        )

        try:
            job = self.client.load_table_from_dataframe(
                df,
                self.table_ref,
                job_config=job_config,
            )
            job.result()

            if job.errors:
                raise RuntimeError(
                    f"BQ load completed with errors — "
                    f"job_id: {job.job_id}, errors: {job.errors}"
                )

            log.info(
                f"BQ load complete — "
                f"rows: {len(df)}, job_id: {job.job_id}"
            )
            return len(df), job.job_id

        except GoogleAPIError as exc:
            log.error(f"BigQuery API error — {exc}")
            raise

    def setup_and_load(self, df: pd.DataFrame) -> tuple:
        """
        Ensures infrastructure exists then loads.
        Safe to call on every run — no-op if table already exists.
        """
        self.ensure_dataset_exists()
        self.ensure_table_exists()
        return self.load(df)