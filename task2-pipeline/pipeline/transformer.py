import logging
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _safe_diff(
    a: Optional[float],
    b: Optional[float]
) -> Optional[float]:
    if a is None or b is None:
        return None
    return round(a - b, 2)


def _safe_avg(
    a: Optional[float],
    b: Optional[float]
) -> Optional[float]:
    if a is None or b is None:
        return None
    return round((a + b) / 2, 2)


def _calculate_risk_index(
    temp_variance: Optional[float],
    precip_prob:   Optional[float],
    windspeed:     Optional[float],
) -> Optional[float]:
    """
    Composite weather risk score for outdoor and weather-sensitive
    marketing campaigns in Indian metros.

    Components:
      precipitation_prob  — weighted 0.50, monsoon is the dominant
                            risk factor for Indian D2C campaigns
      temp_variance_c     — weighted 0.30, high daily swing affects
                            outdoor footfall and consumer behaviour
      windspeed_kmh       — weighted 0.20, affects outdoor formats

    Each component normalised to [0, 1] before weighting.
    Returns None if any input is missing — partial stays partial.
    """
    if any(v is None for v in [temp_variance, precip_prob, windspeed]):
        return None

    temp_score = min(float(temp_variance) / 15.0, 1.0)
    rain_score = float(precip_prob) / 100.0
    wind_score = min(float(windspeed) / 60.0, 1.0)

    index = (
        (temp_score * 0.30) +
        (rain_score * 0.50) +
        (wind_score * 0.20)
    )
    return round(index, 3)


def _risk_category(index: Optional[float]) -> Optional[str]:
    if index is None:
        return None
    if index >= 0.70:
        return "HIGH"
    if index >= 0.40:
        return "MEDIUM"
    return "LOW"


def transform(
    raw:      dict,
    location: dict,
    run_id:   str,
) -> pd.DataFrame:
    """
    Transforms raw Open-Meteo response into a flat DataFrame.

    One row per day per location. Null handling is explicit throughout
    — no silent coercions. Type casting happens in one pass at the end
    to keep the row-building loop readable.

    Args:
        raw:      Validated API response dict from fetcher
        location: Location config dict — name, lat, lon
        run_id:   Pipeline run UUID for row-level traceability

    Returns:
        pd.DataFrame ready for validator and BigQuery load
    """
    daily       = raw["daily"]
    ingested_at = datetime.now(timezone.utc)
    rows: List[Dict] = []

    dates    = daily["time"]
    temp_max = daily["temperature_2m_max"]
    temp_min = daily["temperature_2m_min"]
    precip   = daily["precipitation_sum"]
    precip_p = daily["precipitation_probability_max"]
    wind     = daily["windspeed_10m_max"]
    wcode    = daily["weathercode"]

    for i, date in enumerate(dates):
        t_max  = temp_max[i]
        t_min  = temp_min[i]
        t_var  = _safe_diff(t_max, t_min)
        t_avg  = _safe_avg(t_max, t_min)
        p_sum  = precip[i]
        p_prob = precip_p[i]
        w_spd  = wind[i]
        w_code = wcode[i]

        risk_idx = _calculate_risk_index(t_var, p_prob, w_spd)

        rows.append({
            "fetch_date":          pd.to_datetime(date).date(),
            "location":            location["name"],
            "country":             "India",
            "latitude":            location["lat"],
            "longitude":           location["lon"],
            "avg_temp_c":          t_avg,
            "max_temp_c":          t_max,
            "min_temp_c":          t_min,
            "temp_variance_c":     t_var,
            "precipitation_mm":    p_sum,
            "precipitation_prob":  p_prob,
            "windspeed_kmh":       w_spd,
            # stored as float64 — pandas nullable Int64 serializes
            # inconsistently with pyarrow across library versions
            "weathercode":         float(w_code) if w_code is not None else None,
            "campaign_risk_index": risk_idx,
            "risk_category":       _risk_category(risk_idx),
            "pipeline_run_id":     run_id,
            "ingested_at":         ingested_at,
        })

    df = pd.DataFrame(rows)

    # Type enforcement in one pass
    # fetch_date kept as datetime64 for reliable
    # pyarrow → BigQuery DATE serialization
    df["fetch_date"] = pd.to_datetime(df["fetch_date"])
    df["ingested_at"] = pd.to_datetime(df["ingested_at"], utc=True)

    for col in [
        "avg_temp_c", "max_temp_c", "min_temp_c",
        "temp_variance_c", "precipitation_mm",
        "precipitation_prob", "windspeed_kmh",
        "campaign_risk_index", "weathercode",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    avg_risk     = df["campaign_risk_index"].mean()
    avg_risk_str = f"{avg_risk:.3f}" if pd.notna(avg_risk) else "N/A"

    log.info(
        f"Transform complete — "
        f"location: {location['name']}, "
        f"rows: {len(df)}, "
        f"avg_risk_index: {avg_risk_str}"
    )
    return df