CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etl_run (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    code_version TEXT,
    source_dataset_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    note TEXT
);

CREATE TABLE IF NOT EXISTS provider_payload (
    payload_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    dataset TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    request_fingerprint TEXT,
    http_status SMALLINT,
    payload JSONB,
    expires_at TIMESTAMPTZ,
    terms_verified BOOLEAN NOT NULL DEFAULT false,
    CHECK (payload IS NULL OR (terms_verified AND expires_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS provider_payload_expiry_idx ON provider_payload (expires_at);

CREATE TABLE IF NOT EXISTS area (
    area_id TEXT PRIMARY KEY,
    spatial_scope TEXT NOT NULL CHECK (spatial_scope IN ('point_sample', 'grid_cell', 'polygon')),
    representative_point geometry(Point, 4326) NOT NULL,
    coverage geometry(Geometry, 4326),
    timezone_name TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    source_dataset_id TEXT,
    etl_run_id UUID NOT NULL REFERENCES etl_run(run_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS area_point_gix ON area USING GIST (representative_point);
CREATE INDEX IF NOT EXISTS area_coverage_gix ON area USING GIST (coverage);

CREATE TABLE IF NOT EXISTS weather_forecast (
    observation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    area_id TEXT NOT NULL REFERENCES area(area_id) ON DELETE CASCADE,
    provider_location geometry(Point, 4326) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    valid_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    precipitation_probability_pct NUMERIC(5,2),
    precipitation_mm NUMERIC(8,3),
    etl_run_id UUID NOT NULL REFERENCES etl_run(run_id),
    source_dataset_id TEXT NOT NULL,
    raw_payload_id BIGINT REFERENCES provider_payload(payload_id) ON DELETE SET NULL,
    CHECK (precipitation_probability_pct IS NULL OR precipitation_probability_pct BETWEEN 0 AND 100),
    CHECK (precipitation_mm IS NULL OR precipitation_mm >= 0),
    UNIQUE (provider, area_id, issued_at, valid_at, fetched_at)
);
CREATE INDEX IF NOT EXISTS weather_area_valid_idx ON weather_forecast (area_id, valid_at DESC, fetched_at DESC);

CREATE TABLE IF NOT EXISTS poi_feature (
    poi_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    source_feature_id TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    name TEXT,
    point_method TEXT,
    geom geometry(Point, 4326) NOT NULL,
    tags JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at TIMESTAMPTZ NOT NULL,
    etl_run_id UUID NOT NULL REFERENCES etl_run(run_id),
    source_dataset_id TEXT NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (provider, source_feature_id)
);
CREATE INDEX IF NOT EXISTS poi_feature_geom_gix ON poi_feature USING GIST (geom);
CREATE INDEX IF NOT EXISTS poi_feature_category_idx ON poi_feature (category, subcategory) WHERE is_current;

CREATE TABLE IF NOT EXISTS poi_grid_cell (
    cell_id TEXT PRIMARY KEY,
    parent_area_id TEXT NOT NULL REFERENCES area(area_id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL CHECK (row_number >= 0),
    column_number INTEGER NOT NULL CHECK (column_number >= 0),
    center geometry(Point, 4326) NOT NULL,
    geom geometry(Polygon, 4326) NOT NULL,
    cell_size_m INTEGER NOT NULL CHECK (cell_size_m > 0),
    cell_area_km2 NUMERIC(12,8) NOT NULL CHECK (cell_area_km2 >= 0),
    cafe_poi_count INTEGER NOT NULL CHECK (cafe_poi_count >= 0),
    cafe_density_per_km2 NUMERIC(14,4) NOT NULL CHECK (cafe_density_per_km2 >= 0),
    cafe_poi_count_within_500m INTEGER CHECK (cafe_poi_count_within_500m >= 0),
    cafe_count_500m_status TEXT NOT NULL CHECK (cafe_count_500m_status IN ('full_coverage', 'partial_coverage')),
    etl_run_id UUID NOT NULL REFERENCES etl_run(run_id),
    source_dataset_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS poi_grid_cell_geom_gix ON poi_grid_cell USING GIST (geom);

CREATE TABLE IF NOT EXISTS waiting_location_candidate (
    candidate_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    source_id TEXT NOT NULL,
    osm_type TEXT,
    osm_id TEXT,
    name TEXT,
    poi_type TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'waiting_location_candidate' CHECK (role = 'waiting_location_candidate'),
    candidate_status TEXT NOT NULL DEFAULT 'unverified_candidate',
    permission_to_wait TEXT NOT NULL DEFAULT 'unknown',
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    geom geometry(Point, 4326) NOT NULL,
    point_method TEXT NOT NULL,
    area_m2 NUMERIC(14,2) CHECK (area_m2 IS NULL OR area_m2 >= 0),
    verification_needed JSONB NOT NULL DEFAULT '[]'::jsonb,
    categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    address TEXT,
    tags JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at TIMESTAMPTZ NOT NULL,
    etl_run_id UUID NOT NULL REFERENCES etl_run(run_id),
    source_dataset_id TEXT NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS waiting_candidate_geom_gix ON waiting_location_candidate USING GIST (geom);

CREATE TABLE IF NOT EXISTS route_observation (
    route_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    area_id TEXT NOT NULL REFERENCES area(area_id) ON DELETE CASCADE,
    destination_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    profile TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    route_distance_m NUMERIC(12,2),
    route_duration_s NUMERIC(12,2),
    origin geometry(Point, 4326),
    destination geometry(Point, 4326),
    route_geom geometry(LineString, 4326),
    etl_run_id UUID NOT NULL REFERENCES etl_run(run_id),
    source_dataset_id TEXT NOT NULL,
    raw_payload_id BIGINT REFERENCES provider_payload(payload_id) ON DELETE SET NULL,
    CHECK (route_distance_m IS NULL OR route_distance_m >= 0),
    CHECK (route_duration_s IS NULL OR route_duration_s >= 0),
    UNIQUE (area_id, destination_id, provider, profile, fetched_at)
);
CREATE INDEX IF NOT EXISTS route_area_fetched_idx ON route_observation (area_id, fetched_at DESC);

CREATE TABLE IF NOT EXISTS traffic_flow_observation (
    observation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    query_point geometry(Point, 4326) NOT NULL,
    segment_geom geometry(Geometry, 4326),
    current_speed_kph NUMERIC(8,2),
    free_flow_speed_kph NUMERIC(8,2),
    current_travel_time_s NUMERIC(12,2),
    free_flow_travel_time_s NUMERIC(12,2),
    confidence NUMERIC(5,2),
    road_closed BOOLEAN,
    functional_road_class TEXT,
    openlr TEXT,
    etl_run_id UUID NOT NULL REFERENCES etl_run(run_id),
    raw_payload_id BIGINT REFERENCES provider_payload(payload_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS traffic_flow_fetched_idx ON traffic_flow_observation (fetched_at DESC);
CREATE INDEX IF NOT EXISTS traffic_flow_geom_gix ON traffic_flow_observation USING GIST (segment_geom);

CREATE TABLE IF NOT EXISTS traffic_incident_observation (
    observation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_incident_id TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    category TEXT,
    delay_magnitude TEXT,
    delay_s INTEGER,
    length_m NUMERIC(12,2),
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    time_validity TEXT,
    geom geometry(Geometry, 4326),
    etl_run_id UUID NOT NULL REFERENCES etl_run(run_id),
    raw_payload_id BIGINT REFERENCES provider_payload(payload_id) ON DELETE SET NULL,
    UNIQUE (provider, provider_incident_id, fetched_at)
);
CREATE INDEX IF NOT EXISTS traffic_incident_fetched_idx ON traffic_incident_observation (fetched_at DESC);
CREATE INDEX IF NOT EXISTS traffic_incident_geom_gix ON traffic_incident_observation USING GIST (geom);
