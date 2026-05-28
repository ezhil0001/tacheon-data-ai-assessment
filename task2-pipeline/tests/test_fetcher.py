import pytest
from unittest.mock import patch, MagicMock
import requests

from pipeline.fetcher import (
    _fetch_with_retry,
    _build_params,
    fetch_all_locations,
    NON_RETRYABLE_STATUS,
)
from config import settings


# ── Helpers ───────────────────────────────────────────────────

LOCATION = {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777}


def make_mock_response(status_code: int = 200, json_data: dict = None) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data or {
        "daily": {
            "time": ["2026-05-20"],
            "temperature_2m_max": [34.1],
            "temperature_2m_min": [24.0],
            "precipitation_sum": [0.0],
            "precipitation_probability_max": [10],
            "windspeed_10m_max": [12.0],
            "weathercode": [1],
        }
    }
    if status_code != 200:
        http_error = requests.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_error
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


# ── Param building ────────────────────────────────────────────

class TestBuildParams:

    def test_required_keys_present(self):
        params = _build_params(LOCATION)
        assert "latitude"  in params
        assert "longitude" in params
        assert "daily"     in params
        assert "timezone"  in params
        assert "past_days" in params

    def test_coordinates_match_location(self):
        params = _build_params(LOCATION)
        assert params["latitude"]  == LOCATION["lat"]
        assert params["longitude"] == LOCATION["lon"]

    def test_timezone_is_kolkata(self):
        params = _build_params(LOCATION)
        assert params["timezone"] == "Asia/Kolkata"

    def test_past_days_from_settings(self):
        params = _build_params(LOCATION)
        assert params["past_days"] == settings.FETCH_PAST_DAYS


# ── Retry behaviour ───────────────────────────────────────────

class TestFetchWithRetry:

    def test_success_on_first_attempt(self):
        session = MagicMock()
        session.get.return_value = make_mock_response(200)

        result = _fetch_with_retry(session, LOCATION)
        assert "daily" in result
        assert session.get.call_count == 1

    def test_retries_on_503(self):
        session      = MagicMock()
        fail_resp    = make_mock_response(503)
        success_resp = make_mock_response(200)

        # Fail twice then succeed
        session.get.side_effect = [fail_resp, fail_resp, success_resp]

        with patch("pipeline.fetcher.time.sleep"):
            result = _fetch_with_retry(session, LOCATION)

        assert "daily" in result
        assert session.get.call_count == 3

    def test_raises_after_all_retries_exhausted(self):
        session = MagicMock()
        session.get.return_value = make_mock_response(503)

        with patch("pipeline.fetcher.time.sleep"):
            with pytest.raises(RuntimeError, match="retries exhausted"):
                _fetch_with_retry(session, LOCATION)

    def test_no_retry_on_400(self):
        session = MagicMock()
        session.get.return_value = make_mock_response(400)

        with pytest.raises(requests.exceptions.HTTPError):
            _fetch_with_retry(session, LOCATION)

        assert session.get.call_count == 1

    def test_no_retry_on_404(self):
        session = MagicMock()
        session.get.return_value = make_mock_response(404)

        with pytest.raises(requests.exceptions.HTTPError):
            _fetch_with_retry(session, LOCATION)

        assert session.get.call_count == 1

    def test_retries_on_timeout(self):
        session = MagicMock()
        session.get.side_effect = [
            requests.exceptions.Timeout(),
            requests.exceptions.Timeout(),
            make_mock_response(200),
        ]

        with patch("pipeline.fetcher.time.sleep"):
            result = _fetch_with_retry(session, LOCATION)

        assert "daily" in result
        assert session.get.call_count == 3

    def test_retries_on_connection_error(self):
        session = MagicMock()
        session.get.side_effect = [
            requests.exceptions.ConnectionError(),
            make_mock_response(200),
        ]

        with patch("pipeline.fetcher.time.sleep"):
            result = _fetch_with_retry(session, LOCATION)

        assert "daily" in result
        assert session.get.call_count == 2

    def test_exponential_backoff_applied(self):
        session = MagicMock()
        session.get.return_value = make_mock_response(503)

        sleep_calls = []
        with patch("pipeline.fetcher.time.sleep", side_effect=sleep_calls.append):
            with pytest.raises(RuntimeError):
                _fetch_with_retry(session, LOCATION)

        # Wait doubles each retry — 2s then 4s
        assert sleep_calls[0] == settings.RETRY_WAIT_SECONDS
        assert sleep_calls[1] == settings.RETRY_WAIT_SECONDS * 2


# ── Non-retryable status codes ────────────────────────────────

class TestNonRetryableStatus:

    def test_all_expected_codes_present(self):
        assert 400 in NON_RETRYABLE_STATUS
        assert 401 in NON_RETRYABLE_STATUS
        assert 403 in NON_RETRYABLE_STATUS
        assert 404 in NON_RETRYABLE_STATUS
        assert 422 in NON_RETRYABLE_STATUS

    def test_503_not_in_non_retryable(self):
        assert 503 not in NON_RETRYABLE_STATUS


# ── fetch_all_locations ───────────────────────────────────────

class TestFetchAllLocations:

    @patch("pipeline.fetcher._build_session")
    @patch("pipeline.fetcher._fetch_with_retry")
    def test_returns_all_locations_on_success(
        self, mock_fetch, mock_session
    ):
        mock_fetch.return_value = {"daily": {"time": ["2026-05-20"]}}
        mock_session.return_value = MagicMock()

        results = fetch_all_locations()
        assert len(results) == len(settings.LOCATIONS)

    @patch("pipeline.fetcher._build_session")
    @patch("pipeline.fetcher._fetch_with_retry")
    def test_partial_failure_continues(
        self, mock_fetch, mock_session
    ):
        mock_session.return_value = MagicMock()

        # First location fails, rest succeed
        def side_effect(session, location):
            if location["name"] == "Mumbai":
                raise RuntimeError("Simulated failure")
            return {"daily": {"time": ["2026-05-20"]}}

        mock_fetch.side_effect = side_effect
        results = fetch_all_locations()

        # 4 of 5 locations should still load
        assert len(results) == len(settings.LOCATIONS) - 1

    @patch("pipeline.fetcher._build_session")
    @patch("pipeline.fetcher._fetch_with_retry")
    def test_raises_when_all_fail(
        self, mock_fetch, mock_session
    ):
        mock_session.return_value = MagicMock()
        mock_fetch.side_effect   = RuntimeError("All failed")

        with pytest.raises(RuntimeError, match="All location fetches failed"):
            fetch_all_locations()