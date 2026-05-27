import os
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value or value == "your-gcp-project-id":
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and fill in the value."
        )
    return value


def _optional(key: str, default: str) -> str:
    return os.getenv(key, default)


class Settings:

    # GCP — project ID is required, everything else has a default
    GCP_PROJECT_ID: str = _require("GCP_PROJECT_ID")
    BQ_DATASET:     str = _optional("BQ_DATASET", "weather_marketing")
    BQ_TABLE:       str = _optional("BQ_TABLE",   "daily_weather")

    # Fetch behaviour
    FETCH_PAST_DAYS:    int = int(_optional("FETCH_PAST_DAYS",      "7"))
    MAX_RETRIES:        int = int(_optional("MAX_RETRIES",           "3"))
    RETRY_WAIT_SECONDS: int = int(_optional("RETRY_WAIT_SECONDS",    "2"))
    REQUEST_TIMEOUT:    int = int(_optional("REQUEST_TIMEOUT",      "10"))

    # Five Indian metros — covers the major D2C marketing markets
    # and gives meaningful regional variance in weather patterns
    LOCATIONS: List[Dict] = [
        {"name": "Mumbai",    "lat": 19.0760, "lon": 72.8777},
        {"name": "Delhi",     "lat": 28.6139, "lon": 77.2090},
        {"name": "Bangalore", "lat": 12.9716, "lon": 77.5946},
        {"name": "Chennai",   "lat": 13.0827, "lon": 80.2707},
        {"name": "Kolkata",   "lat": 22.5726, "lon": 88.3639},
    ]

    # Open-Meteo daily variables to request
    DAILY_VARIABLES: List[str] = [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "windspeed_10m_max",
        "weathercode",
    ]


settings = Settings()