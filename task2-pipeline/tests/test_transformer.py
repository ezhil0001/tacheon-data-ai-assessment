import pytest
import pandas as pd
from pipeline.transformer import (
    transform,
    _calculate_risk_index,
    _risk_category,
    _safe_diff,
    _safe_avg,
)

# ── Fixtures ──────────────────────────────────────────────────

LOCATION = {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777}
RUN_ID   = "test-run-001"


def make_response(days: int = 2) -> dict:
    """Minimal valid Open-Meteo response for testing."""

    return {
        "daily": {
            "time": [
                f"2026-05-{20+i:02d}" for i in range(days)
            ],
            "temperature_2m_max": [
                34.0 + i for i in range(days)
            ],
            "temperature_2m_min": [
                24.0 + i for i in range(days)
            ],
            "precipitation_sum": [
                round(i * 1.2, 1) for i in range(days)
            ],
            "precipitation_probability_max": [
                min(i * 10, 100) for i in range(days)
            ],
            "windspeed_10m_max": [
                12.0 + i for i in range(days)
            ],
            "weathercode": [
                1 if i % 2 == 0 else 61
                for i in range(days)
            ],
        }
    }


# ── Helper function tests ──────────────────────────────────────

class TestSafeDiff:

    def test_both_values_present(self):
        assert _safe_diff(34.1, 24.0) == 10.1

    def test_first_value_none(self):
        assert _safe_diff(None, 24.0) is None

    def test_second_value_none(self):
        assert _safe_diff(34.1, None) is None

    def test_both_none(self):
        assert _safe_diff(None, None) is None

    def test_rounding(self):
        result = _safe_diff(34.123, 24.456)
        assert result == round(34.123 - 24.456, 2)


class TestSafeAvg:

    def test_both_values_present(self):
        assert _safe_avg(34.0, 24.0) == 29.0

    def test_either_none_returns_none(self):
        assert _safe_avg(None, 24.0) is None
        assert _safe_avg(34.0, None) is None


class TestCalculateRiskIndex:

    def test_all_zero_inputs(self):
        result = _calculate_risk_index(0.0, 0.0, 0.0)
        assert result == 0.0

    def test_all_max_inputs(self):
        # temp_variance >= 15, precip_prob = 100, wind >= 60
        result = _calculate_risk_index(15.0, 100.0, 60.0)
        assert result == 1.0

    def test_partial_none_returns_none(self):
        assert _calculate_risk_index(None, 60.0, 12.0) is None
        assert _calculate_risk_index(10.0, None, 12.0) is None
        assert _calculate_risk_index(10.0, 60.0, None) is None

    def test_result_within_bounds(self):
        result = _calculate_risk_index(10.1, 10.0, 12.0)
        assert result is not None
        assert 0.0 <= result <= 1.0

    def test_manual_calculation(self):
        # temp_variance=10.1, precip_prob=10, windspeed=12.0
        # temp_score  = min(10.1/15, 1.0) = 0.6733
        # rain_score  = 10/100 = 0.10
        # wind_score  = min(12.0/60, 1.0) = 0.20
        # index = (0.6733*0.30) + (0.10*0.50) + (0.20*0.20)
        #       = 0.202 + 0.05 + 0.04 = 0.292
        result = _calculate_risk_index(10.1, 10.0, 12.0)
        assert result == pytest.approx(0.292, abs=0.001)

    def test_high_variance_capped_at_one(self):
        # temp_variance > 15 should not push score above 1.0
        result = _calculate_risk_index(30.0, 100.0, 120.0)
        assert result == 1.0


class TestRiskCategory:

    def test_high_category(self):
        assert _risk_category(0.70) == "HIGH"
        assert _risk_category(0.95) == "HIGH"

    def test_medium_category(self):
        assert _risk_category(0.40) == "MEDIUM"
        assert _risk_category(0.69) == "MEDIUM"

    def test_low_category(self):
        assert _risk_category(0.0)  == "LOW"
        assert _risk_category(0.29) == "LOW"

    def test_none_returns_none(self):
        assert _risk_category(None) is None


# ── Transform integration tests ────────────────────────────────

class TestTransform:

    def test_output_shape(self):
        df = transform(make_response(2), LOCATION, RUN_ID)
        assert len(df) == 2
        assert "campaign_risk_index" in df.columns
        assert "risk_category" in df.columns
        assert "pipeline_run_id" in df.columns

    def test_row_count_matches_days(self):
        for days in [1, 5, 8]:
            df = transform(make_response(days), LOCATION, RUN_ID)
            assert len(df) == days

    def test_location_populated(self):
        df = transform(make_response(), LOCATION, RUN_ID)
        assert (df["location"] == "Mumbai").all()
        assert (df["country"] == "India").all()

    def test_run_id_on_every_row(self):
        df = transform(make_response(), LOCATION, RUN_ID)
        assert (df["pipeline_run_id"] == RUN_ID).all()

    def test_risk_index_within_bounds(self):
        df = transform(make_response(), LOCATION, RUN_ID)
        valid = df["campaign_risk_index"].dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 1.0).all()

    def test_fetch_date_is_datetime(self):
        df = transform(make_response(), LOCATION, RUN_ID)

        assert str(df["fetch_date"].dtype).startswith("datetime64")
        assert str(df["fetch_date"].iloc[0].date()) == "2026-05-20"

    def test_weathercode_is_float(self):
        # pandas nullable Int64 causes pyarrow serialization issues
        df = transform(make_response(), LOCATION, RUN_ID)
        assert df["weathercode"].dtype == float

    def test_numeric_columns_are_numeric(self):
        df = transform(make_response(), LOCATION, RUN_ID)
        for col in ["avg_temp_c", "max_temp_c", "temp_variance_c",
                    "precipitation_mm", "campaign_risk_index"]:
            assert pd.api.types.is_numeric_dtype(df[col]), \
                f"Expected numeric dtype for {col}"

    def test_null_inputs_produce_null_risk(self):
        response = make_response(1)
        response["daily"]["temperature_2m_max"] = [None]
        df = transform(response, LOCATION, RUN_ID)
        assert pd.isna(df["campaign_risk_index"].iloc[0])
        assert pd.isna(df["risk_category"].iloc[0])

    def test_ingested_at_is_utc(self):
        df = transform(make_response(), LOCATION, RUN_ID)
        assert str(df["ingested_at"].dtype) == "datetime64[ns, UTC]"