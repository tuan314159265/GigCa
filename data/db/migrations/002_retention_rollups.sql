CREATE TABLE IF NOT EXISTS traffic_flow_hourly_summary (
    bucket_start TIMESTAMPTZ NOT NULL,
    provider TEXT NOT NULL,
    cell_key TEXT NOT NULL,
    segment_cell geometry(Polygon, 4326) NOT NULL,
    sample_count INTEGER NOT NULL,
    median_current_speed_kph NUMERIC(8,2),
    median_free_flow_speed_kph NUMERIC(8,2),
    median_congestion_ratio NUMERIC(8,4),
    PRIMARY KEY (bucket_start, provider, cell_key)
);
CREATE INDEX IF NOT EXISTS traffic_flow_summary_geom_gix ON traffic_flow_hourly_summary USING GIST (segment_cell);

CREATE TABLE IF NOT EXISTS traffic_incident_daily_summary (
    bucket_date DATE NOT NULL,
    provider TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'unknown',
    severity TEXT NOT NULL DEFAULT 'unknown',
    incident_count INTEGER NOT NULL,
    observed_delay_s BIGINT NOT NULL DEFAULT 0,
    affected_length_m NUMERIC(14,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket_date, provider, category, severity)
);
