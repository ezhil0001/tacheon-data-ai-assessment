import logging
import pandas as pd
from typing import List

log = logging.getLogger(__name__)

# Fields we expect Open-Meteo to return inside the daily block.
# If any are missing the API has changed and we should fail loudly
# rather than silently produce incomplete rows downstream.
REQUIRED_DAILY_FIELDS: List[str] = [
    "time",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "windspeed_10m_max",
    "weathercode",
]

# Columns that must exist in the DataFrame after transformation.
REQUIRED_DF_COLUMNS: List[str] = [
    "fetch_date",
    "location",
    "campaign_risk_index",
    "pipeline_run_id",
    "ingested_at",
]

# Columns where a null value means the row is unusable.
NON_NULLABLE_COLUMNS: List[str] = [
    "fetch_date",
    "location",
    "pipeline_run_id",
    "ingested_at",
]


def validate_api_response(data: dict, location_name: str) -> None:
    """
    Validates raw API response structure before transformation.

    Raises ValueError with a clear message if anything unexpected
    is found. Designed to surface API schema changes early rather
    than letting bad data propagate into the transform layer.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"API response is not a dict — "
            f"location: {location_name}, got: {type(data).__name__}"
        )

    if "daily" not in data:
        raise ValueError(
            f"Missing 'daily' key in response — "
            f"location: {location_name}"
        )

    daily = data["daily"]

    missing = [f for f in REQUIRED_DAILY_FIELDS if f not in daily]
    if missing:
        raise ValueError(
            f"Missing fields in daily response — "
            f"location: {location_name}, fields: {missing}"
        )

    time_series = daily.get("time", [])
    if not time_series:
        raise ValueError(
            f"Empty time series in response — "
            f"location: {location_name}"
        )

    # Array length consistency — if one field has fewer entries than
    # time, the rows won't align correctly after flattening
    expected_len = len(time_series)
    for field in REQUIRED_DAILY_FIELDS:
        actual_len = len(daily[field])
        if actual_len != expected_len:
            raise ValueError(
                f"Array length mismatch in '{field}' — "
                f"location: {location_name}, "
                f"expected: {expected_len}, got: {actual_len}"
            )

    log.info(
        f"Response validation passed — "
        f"location: {location_name}, days: {expected_len}"
    )


def validate_dataframe(df: pd.DataFrame, location_name: str) -> None:
    """
    Validates transformed DataFrame before BigQuery load.

    Catches empty DataFrames, missing columns, nulls in required
    fields, out-of-bounds risk scores, and duplicate date rows.
    """
    if df.empty:
        raise ValueError(
            f"Empty DataFrame after transformation — "
            f"location: {location_name}"
        )

    missing_cols = [
        c for c in REQUIRED_DF_COLUMNS if c not in df.columns
    ]
    if missing_cols:
        raise ValueError(
            f"Missing columns after transformation — "
            f"location: {location_name}, columns: {missing_cols}"
        )

    for col in NON_NULLABLE_COLUMNS:
        null_count = df[col].isna().sum()
        if null_count > 0:
            raise ValueError(
                f"Null values in non-nullable column '{col}' — "
                f"location: {location_name}, count: {null_count}"
            )

    # campaign_risk_index should always be within [0, 1]
    # if it isn't, the calculation logic has a bug
    invalid_risk = df[
        df["campaign_risk_index"].notna() &
        (
            (df["campaign_risk_index"] < 0) |
            (df["campaign_risk_index"] > 1)
        )
    ]
    if not invalid_risk.empty:
        raise ValueError(
            f"campaign_risk_index out of bounds [0, 1] — "
            f"location: {location_name}, "
            f"rows: {len(invalid_risk)}, "
            f"values: {invalid_risk['campaign_risk_index'].tolist()}"
        )

    # Duplicate dates for the same location means something went
    # wrong in the flatten step — each date should appear once
    duplicates = df.duplicated(subset=["fetch_date", "location"])
    if duplicates.any():
        raise ValueError(
            f"Duplicate rows found for (fetch_date, location) — "
            f"location: {location_name}, "
            f"count: {duplicates.sum()}"
        )

    log.info(
        f"DataFrame validation passed — "
        f"location: {location_name}, rows: {len(df)}"
    )