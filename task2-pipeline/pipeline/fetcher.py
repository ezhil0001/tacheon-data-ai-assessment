import time
import logging
import requests
from typing import List, Dict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings

log = logging.getLogger(__name__)

BASE_URL = "https://api.open-meteo.com/v1/forecast"

# HTTP status codes where retrying will not help
# 4xx logic errors should surface immediately, not be silently retried
NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}


def _build_session() -> requests.Session:
    session = requests.Session()
    # urllib3-level retries disabled — retry logic lives in application
    # layer where we can log each attempt and apply backoff ourselves
    adapter = HTTPAdapter(
        max_retries=Retry(total=0),
        pool_connections=5,
        pool_maxsize=10,
    )
    session.mount("https://", adapter)
    session.headers.update({"Accept": "application/json"})
    return session


def _build_params(location: Dict) -> Dict:
    return {
        "latitude":  location["lat"],
        "longitude": location["lon"],
        "daily":     settings.DAILY_VARIABLES,
        "timezone":  "Asia/Kolkata",
        "past_days": settings.FETCH_PAST_DAYS,
    }


def _fetch_with_retry(
    session:  requests.Session,
    location: Dict,
) -> Dict:
    params     = _build_params(location)
    name       = location["name"]
    wait       = settings.RETRY_WAIT_SECONDS
    last_error = None

    for attempt in range(1, settings.MAX_RETRIES + 1):
        try:
            log.info(
                f"Fetching — location: {name}, "
                f"attempt: {attempt}/{settings.MAX_RETRIES}"
            )
            response = session.get(
                BASE_URL,
                params=params,
                timeout=settings.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            days_returned = len(data.get("daily", {}).get("time", []))
            log.info(
                f"Fetch success — location: {name}, "
                f"days: {days_returned}"
            )
            return data

        except requests.exceptions.Timeout:
            last_error = f"timed out after {settings.REQUEST_TIMEOUT}s"
            log.warning(
                f"Timeout — location: {name}, attempt: {attempt}. "
                f"{last_error}"
            )

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code
            if status in NON_RETRYABLE_STATUS:
                log.error(
                    f"Non-retryable HTTP {status} — location: {name}. "
                    f"Check API params."
                )
                raise
            last_error = f"HTTP {status}"
            log.warning(
                f"Retryable error — location: {name}, "
                f"status: {status}, attempt: {attempt}"
            )

        except requests.exceptions.ConnectionError:
            last_error = "connection error"
            log.warning(
                f"Connection error — location: {name}, "
                f"attempt: {attempt}"
            )

        if attempt < settings.MAX_RETRIES:
            log.info(f"Retrying in {wait}s — location: {name}")
            time.sleep(wait)
            wait *= 2

    raise RuntimeError(
        f"All {settings.MAX_RETRIES} retries exhausted — "
        f"location: {name}. Last error: {last_error}"
    )


def fetch_all_locations() -> List[Dict]:
    """
    Fetches weather data for all configured locations.

    Partial failure strategy: if one location fails after all retries,
    it is skipped with a warning. The pipeline continues with the
    remaining locations. If ALL locations fail, raises RuntimeError.

    Returns:
        List of dicts — [{"location": {...}, "data": {...}}, ...]
    """
    session = _build_session()
    results = []
    failed  = []

    try:
        for location in settings.LOCATIONS:
            try:
                raw = _fetch_with_retry(session, location)
                results.append({"location": location, "data": raw})
            except Exception as exc:
                log.error(
                    f"Location fetch failed permanently — "
                    f"location: {location['name']}, error: {exc}"
                )
                failed.append(location["name"])
    finally:
        session.close()

    if failed:
        log.warning(
            f"Skipped locations due to fetch failure: {failed}"
        )

    if not results:
        raise RuntimeError(
            "All location fetches failed. "
            "Check network connectivity and Open-Meteo availability."
        )

    log.info(
        f"Fetch complete — "
        f"success: {len(results)}, failed: {len(failed)}"
    )
    return results