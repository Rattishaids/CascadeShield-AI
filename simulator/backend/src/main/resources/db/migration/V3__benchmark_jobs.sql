CREATE TABLE benchmark_jobs (
  id uuid PRIMARY KEY,
  network_id text NOT NULL REFERENCES network_versions(id), graph_sha256 text NOT NULL,
  status text NOT NULL CHECK(status IN ('QUEUED','RUNNING','COMPLETED','FAILED')),
  request jsonb NOT NULL, result jsonb, error text,
  completed_runs integer NOT NULL DEFAULT 0, total_runs integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
  provenance text NOT NULL CHECK(provenance='SIMULATED_RESEARCH_EXPERIMENT')
);
COMMENT ON TABLE benchmark_jobs IS 'Isolated generated simulation experiments; no live state or historical freight rows are modified.';
