-- ============================================================
-- Marketing Campaign Weather Risk Analysis
-- Dataset: weather_marketing.daily_weather
-- Project: hospital-review-455006
--
-- Purpose: Help marketing teams understand weather-related
--          campaign risk across Indian metros
--
-- All queries compatible with BigQuery Sandbox
-- ============================================================


-- ============================================================
-- QUERY 1: Weekly campaign risk summary by city
--
-- Primary operational query. Answers: which cities had the
-- highest weather risk this month, and on how many days was
-- risk elevated enough to affect campaign decisions?
--
-- A team running outdoor or weather-sensitive campaigns in
-- Mumbai and Delhi would use this to decide where to increase
-- digital spend as a weather hedge.
-- ============================================================

SELECT
    location,
    DATE_TRUNC(fetch_date, WEEK)            AS week_start,
    ROUND(AVG(campaign_risk_index), 3)      AS avg_risk_score,
    ROUND(AVG(avg_temp_c), 1)               AS avg_temp_c,
    ROUND(AVG(precipitation_prob), 1)       AS avg_precip_prob_pct,
    ROUND(SUM(precipitation_mm), 1)         AS total_rainfall_mm,
    COUNTIF(campaign_risk_index >= 0.70)    AS high_risk_days,
    COUNTIF(campaign_risk_index BETWEEN
            0.40 AND 0.69)                  AS medium_risk_days,
    COUNTIF(campaign_risk_index < 0.30)     AS low_risk_days
FROM
    `hospital-review-455006.weather_marketing.daily_weather`
WHERE
    fetch_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY
    location,
    week_start
ORDER BY
    week_start DESC,
    avg_risk_score DESC;


-- ============================================================
-- QUERY 2: City risk ranking — current week
--
-- Snapshot of where campaign risk sits right now across all
-- five metros. Useful for the Monday morning question:
-- "Where should we be careful with outdoor spend this week?"
-- ============================================================

SELECT
    location,
    ROUND(AVG(campaign_risk_index), 3)      AS avg_risk_this_week,
    ROUND(AVG(avg_temp_c), 1)               AS avg_temp_c,
    ROUND(AVG(precipitation_prob), 1)       AS avg_rain_probability_pct,
    ROUND(SUM(precipitation_mm), 1)         AS total_rainfall_mm,
    ROUND(AVG(windspeed_kmh), 1)            AS avg_windspeed_kmh,
    -- True dominant category — highest risk day's category
    -- for this location in the current week
    ARRAY_AGG(
        risk_category
        ORDER BY campaign_risk_index DESC
        LIMIT 1
    )[OFFSET(0)]                            AS dominant_risk_category,
    RANK() OVER (
        ORDER BY AVG(campaign_risk_index) DESC
    )                                       AS risk_rank
FROM
    `hospital-review-455006.weather_marketing.daily_weather`
WHERE
    fetch_date >= DATE_TRUNC(CURRENT_DATE(), WEEK)
GROUP BY
    location
ORDER BY
    risk_rank;


-- ============================================================
-- QUERY 3: Day-level risk trend — last 14 days per city
--
-- Shows how risk has moved day by day for each city over the
-- last two weeks. Useful for spotting whether conditions are
-- improving or deteriorating heading into a campaign flight.
-- ============================================================

SELECT
    location,
    fetch_date,
    campaign_risk_index,
    risk_category,
    avg_temp_c,
    precipitation_prob,
    precipitation_mm,
    windspeed_kmh,
    -- 3-day rolling average smooths out single-day spikes
    ROUND(
        AVG(campaign_risk_index) OVER (
            PARTITION BY location
            ORDER BY fetch_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ), 3
    )                                       AS risk_3day_rolling_avg,
    -- Day-over-day movement in risk score
    ROUND(
        campaign_risk_index - LAG(campaign_risk_index) OVER (
            PARTITION BY location
            ORDER BY fetch_date
        ), 3
    )                                       AS risk_delta_vs_yesterday
FROM
    `hospital-review-455006.weather_marketing.daily_weather`
WHERE
    fetch_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
ORDER BY
    location,
    fetch_date DESC;


-- ============================================================
-- QUERY 4: Best and worst campaign days by city — last 30 days
--
-- Identifies specific dates that were lowest and highest risk
-- per city. Useful for post-campaign analysis: did performance
-- dip on high-risk weather days?
-- ============================================================

WITH ranked_days AS (
    SELECT
        location,
        fetch_date,
        campaign_risk_index,
        risk_category,
        avg_temp_c,
        precipitation_mm,
        -- ROW_NUMBER avoids ties producing more than 3 rows
        ROW_NUMBER() OVER (
            PARTITION BY location
            ORDER BY campaign_risk_index DESC
        )                                   AS worst_rank,
        ROW_NUMBER() OVER (
            PARTITION BY location
            ORDER BY campaign_risk_index ASC
        )                                   AS best_rank
    FROM
        `hospital-review-455006.weather_marketing.daily_weather`
    WHERE
        fetch_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
        AND campaign_risk_index IS NOT NULL
)

SELECT
    location,
    ARRAY_AGG(
        STRUCT(fetch_date, campaign_risk_index, risk_category)
        ORDER BY worst_rank
        LIMIT 3
    )                                       AS top_3_worst_days,
    ARRAY_AGG(
        STRUCT(fetch_date, campaign_risk_index, risk_category)
        ORDER BY best_rank
        LIMIT 3
    )                                       AS top_3_best_days
FROM
    ranked_days
GROUP BY
    location
ORDER BY
    location;


-- ============================================================
-- QUERY 5: Heat stress analysis — days above 35°C
--
-- Days above 35°C significantly affect outdoor footfall,
-- delivery operations, and consumer behaviour for categories
-- like food, personal care, and outdoor apparel.
--
-- Useful for Mamaearth (sunscreen), Zomato (delivery demand),
-- boAt (outdoor lifestyle campaigns).
-- ============================================================

SELECT
    location,
    COUNT(*)                                AS total_days,
    COUNTIF(max_temp_c >= 35)               AS heat_stress_days,
    COUNTIF(max_temp_c >= 40)               AS extreme_heat_days,
    ROUND(
        COUNTIF(max_temp_c >= 35) * 100.0
        / NULLIF(COUNT(*), 0), 1
    )                                       AS heat_stress_pct,
    ROUND(MAX(max_temp_c), 1)               AS peak_temp_c,
    ROUND(AVG(max_temp_c), 1)               AS avg_max_temp_c,
    CASE
        WHEN COUNTIF(max_temp_c >= 35) * 100.0
             / NULLIF(COUNT(*), 0) >= 50
        THEN 'HIGH — consider digital-first mix'
        WHEN COUNTIF(max_temp_c >= 35) * 100.0
             / NULLIF(COUNT(*), 0) >= 25
        THEN 'MODERATE — monitor outdoor performance'
        ELSE 'LOW — outdoor conditions acceptable'
    END                                     AS campaign_mix_signal
FROM
    `hospital-review-455006.weather_marketing.daily_weather`
WHERE
    fetch_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY
    location
ORDER BY
    heat_stress_pct DESC;


-- ============================================================
-- QUERY 6: Pipeline data quality audit
--
-- Operational query — not for marketing analysts, for whoever
-- owns the pipeline. Checks each run for completeness: expected
-- locations loaded, null rates per metric, days covered.
--
-- Run this after a new deployment or if downstream reports
-- start showing unexpected gaps.
-- ============================================================

WITH run_summary AS (
    SELECT
        pipeline_run_id,
        DATE(MIN(ingested_at))              AS run_date,
        COUNT(DISTINCT location)            AS locations_loaded,
        COUNT(*)                            AS total_rows,
        ROUND(
            COUNTIF(campaign_risk_index IS NULL) * 100.0
            / NULLIF(COUNT(*), 0), 1
        )                                   AS risk_null_rate_pct,
        ROUND(
            COUNTIF(precipitation_mm IS NULL) * 100.0
            / NULLIF(COUNT(*), 0), 1
        )                                   AS precip_null_rate_pct,
        MIN(fetch_date)                     AS earliest_fetch_date,
        MAX(fetch_date)                     AS latest_fetch_date
    FROM
        `hospital-review-455006.weather_marketing.daily_weather`
    GROUP BY
        pipeline_run_id
)

SELECT
    pipeline_run_id,
    run_date,
    locations_loaded,
    CASE
        WHEN locations_loaded < 5
        THEN CONCAT(
            'WARNING — only ',
            CAST(locations_loaded AS STRING),
            '/5 locations'
        )
        ELSE 'OK'
    END                                     AS location_coverage,
    total_rows,
    risk_null_rate_pct,
    precip_null_rate_pct,
    earliest_fetch_date,
    latest_fetch_date,
    DATE_DIFF(
        latest_fetch_date,
        earliest_fetch_date,
        DAY
    ) + 1                                   AS days_covered
FROM
    run_summary
ORDER BY
    run_date DESC
LIMIT 10;