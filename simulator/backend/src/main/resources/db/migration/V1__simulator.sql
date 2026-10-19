CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE network_versions (
  id text PRIMARY KEY, graph_sha256 text NOT NULL, metadata jsonb NOT NULL,
  imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE road_nodes (
  network_id text NOT NULL REFERENCES network_versions(id), osm_node_id bigint NOT NULL,
  geom geometry(Point,4326) NOT NULL, PRIMARY KEY(network_id,osm_node_id)
);
CREATE INDEX road_nodes_geom_idx ON road_nodes USING gist(geom);
CREATE TABLE road_edges (
  network_id text NOT NULL REFERENCES network_versions(id), id text NOT NULL,
  physical_id text NOT NULL, from_node bigint NOT NULL, to_node bigint NOT NULL,
  osm_way_id bigint NOT NULL, length_m double precision NOT NULL CHECK(length_m>0),
  speed_kph double precision NOT NULL CHECK(speed_kph>0), speed_source text NOT NULL,
  tags jsonb NOT NULL, geom geometry(LineString,4326) NOT NULL,
  PRIMARY KEY(network_id,id)
);
CREATE INDEX road_edges_geom_idx ON road_edges USING gist(geom);
CREATE INDEX road_edges_physical_idx ON road_edges(network_id,physical_id);
CREATE TABLE current_state (
  id integer PRIMARY KEY CHECK(id=1), network_id text NOT NULL REFERENCES network_versions(id),
  state jsonb NOT NULL, checkpoint_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE scenarios (
  id uuid PRIMARY KEY, name text NOT NULL, network_id text NOT NULL REFERENCES network_versions(id),
  configuration jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE simulation_events (
  run_id uuid NOT NULL, sequence bigint NOT NULL, clock_sec double precision NOT NULL,
  event_type text NOT NULL, truck_id text, event jsonb NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(run_id,sequence)
);
COMMENT ON SCHEMA cascadeshield_sim IS 'Real OSM geometry; all trucks, assignments, incidents and outcomes are SIMULATED. No ML or field-effectiveness claims.';
