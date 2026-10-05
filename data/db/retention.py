"""Compact and expire detailed observations using the MVP retention defaults."""

from __future__ import annotations

from uuid import uuid4

from data.db.connection import connect


FLOW_ROLLUP_SQL = """
WITH eligible AS (
    SELECT *, ST_GeoHash(ST_PointOnSurface(COALESCE(segment_geom, query_point)), 6) AS cell_key
    FROM traffic_flow_observation
    WHERE fetched_at < now() - interval '30 days'
), grouped AS (
    SELECT date_trunc('hour', fetched_at) AS bucket_start, provider, cell_key,
           count(*)::integer AS sample_count,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY current_speed_kph)
               FILTER (WHERE current_speed_kph IS NOT NULL) AS median_current_speed_kph,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY free_flow_speed_kph)
               FILTER (WHERE free_flow_speed_kph IS NOT NULL) AS median_free_flow_speed_kph,
           percentile_cont(0.5) WITHIN GROUP (
               ORDER BY current_speed_kph / NULLIF(free_flow_speed_kph, 0)
           ) FILTER (WHERE current_speed_kph IS NOT NULL AND free_flow_speed_kph > 0)
               AS median_congestion_ratio
    FROM eligible
    GROUP BY date_trunc('hour', fetched_at), provider, cell_key
)
INSERT INTO traffic_flow_hourly_summary
    (bucket_start, provider, cell_key, segment_cell, sample_count,
     median_current_speed_kph, median_free_flow_speed_kph, median_congestion_ratio)
SELECT g.bucket_start, g.provider, g.cell_key,
       ST_Envelope(ST_GeomFromGeoHash(g.cell_key))::geometry(Polygon, 4326),
       g.sample_count, g.median_current_speed_kph, g.median_free_flow_speed_kph,
       g.median_congestion_ratio
FROM grouped g
ON CONFLICT (bucket_start, provider, cell_key) DO UPDATE SET
    sample_count = EXCLUDED.sample_count,
    median_current_speed_kph = EXCLUDED.median_current_speed_kph,
    median_free_flow_speed_kph = EXCLUDED.median_free_flow_speed_kph,
    median_congestion_ratio = EXCLUDED.median_congestion_ratio
"""

INCIDENT_ROLLUP_SQL = """
WITH per_incident AS (
    SELECT date_trunc('day', fetched_at)::date AS bucket_date, provider,
           provider_incident_id, COALESCE(category, 'unknown') AS category,
           COALESCE(delay_magnitude, 'unknown') AS severity,
           max(COALESCE(delay_s, 0)) AS observed_delay_s,
           max(COALESCE(length_m, 0)) AS affected_length_m
    FROM traffic_incident_observation
    WHERE fetched_at < now() - interval '30 days'
    GROUP BY date_trunc('day', fetched_at)::date, provider, provider_incident_id,
             COALESCE(category, 'unknown'), COALESCE(delay_magnitude, 'unknown')
), grouped AS (
    SELECT bucket_date, provider, category, severity, count(*)::integer AS incident_count,
           sum(observed_delay_s)::bigint AS observed_delay_s,
           sum(affected_length_m) AS affected_length_m
    FROM per_incident
    GROUP BY bucket_date, provider, category, severity
)
INSERT INTO traffic_incident_daily_summary
    (bucket_date, provider, category, severity, incident_count, observed_delay_s, affected_length_m)
SELECT bucket_date, provider, category, severity, incident_count, observed_delay_s, affected_length_m
FROM grouped
ON CONFLICT (bucket_date, provider, category, severity) DO UPDATE SET
    incident_count = EXCLUDED.incident_count,
    observed_delay_s = EXCLUDED.observed_delay_s,
    affected_length_m = EXCLUDED.affected_length_m
"""


def compact_and_expire(database_url: str | None = None) -> dict[str, int]:
    """Roll up old traffic details, then purge expired details and old forecasts.

    Traffic detail is retained for 30 days, route detail for 7 days, and
    weather vintages for at most 30 days. Raw payload bodies expire only when
    an explicit ``expires_at`` was configured; provider terms always take
    precedence over these project defaults.
    """
    run_id = uuid4()
    counts: dict[str, int] = {}
    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO etl_run (run_id, started_at, status, source_dataset_ids, note) "
                "VALUES (%s, now(), 'running', '[]'::jsonb, 'Retention and compaction')",
                (run_id,),
            )
            cursor.execute(FLOW_ROLLUP_SQL)
            cursor.execute("DELETE FROM traffic_flow_observation WHERE fetched_at < now() - interval '30 days'")
            counts["traffic_flow_detail_deleted"] = cursor.rowcount

            cursor.execute(INCIDENT_ROLLUP_SQL)
            cursor.execute("DELETE FROM traffic_incident_observation WHERE fetched_at < now() - interval '30 days'")
            counts["traffic_incident_detail_deleted"] = cursor.rowcount

            cursor.execute("DELETE FROM route_observation WHERE fetched_at < now() - interval '7 days'")
            counts["route_detail_deleted"] = cursor.rowcount
            cursor.execute(
                "DELETE FROM weather_forecast WHERE valid_at < now() - interval '30 days' "
                "AND issued_at < now() - interval '30 days'"
            )
            counts["weather_rows_deleted"] = cursor.rowcount
            cursor.execute(
                "DELETE FROM provider_payload WHERE expires_at IS NOT NULL AND expires_at <= now()"
            )
            counts["expired_payloads_deleted"] = cursor.rowcount
            cursor.execute(
                "DELETE FROM traffic_flow_hourly_summary WHERE bucket_start < now() - interval '365 days'"
            )
            counts["traffic_flow_summaries_deleted"] = cursor.rowcount
            cursor.execute(
                "DELETE FROM traffic_incident_daily_summary WHERE bucket_date < current_date - 365"
            )
            counts["traffic_incident_summaries_deleted"] = cursor.rowcount
            cursor.execute(
                "UPDATE etl_run SET status = 'succeeded', finished_at = now(), note = %s WHERE run_id = %s",
                (f"Retention completed; deleted row counts: {counts}", run_id),
            )
    return counts


if __name__ == "__main__":
    print(compact_and_expire())
