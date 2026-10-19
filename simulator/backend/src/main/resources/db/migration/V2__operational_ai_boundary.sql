CREATE TABLE operational_resources (
  run_id uuid NOT NULL, resource_type text NOT NULL,
  resource_id text NOT NULL, definition jsonb NOT NULL,
  provenance text NOT NULL CHECK (provenance='SIMULATED'),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(run_id,resource_type,resource_id)
);
CREATE TABLE operational_assignments (
  run_id uuid NOT NULL, truck_id text NOT NULL, assignment jsonb NOT NULL,
  provenance text NOT NULL CHECK (provenance='SIMULATED'),
  PRIMARY KEY(run_id,truck_id)
);
CREATE TABLE graph_snapshots (
  id uuid PRIMARY KEY, schema_version text NOT NULL, network_id text NOT NULL REFERENCES network_versions(id),
  run_id uuid NOT NULL, scenario_id uuid REFERENCES scenarios(id), clock_sec double precision NOT NULL,
  snapshot jsonb NOT NULL, operations_provenance text NOT NULL CHECK (operations_provenance='SIMULATED'),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE operator_approvals (
  id uuid PRIMARY KEY, run_id uuid NOT NULL, clock_sec double precision NOT NULL,
  status text NOT NULL CHECK(status IN ('REQUESTED','APPROVED','EXECUTED')),
  state_fingerprint text NOT NULL, candidate jsonb NOT NULL, evaluation jsonb NOT NULL,
  approved_by text, requested_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz, executed_at timestamptz,
  provenance text NOT NULL CHECK(provenance='SIMULATED_OPERATOR_WORKFLOW')
);
COMMENT ON TABLE operational_resources IS 'Projection of authoritative simulated current_state; no observed freight relationships.';
COMMENT ON TABLE operator_approvals IS 'Local operator approval audit; future AI read tools cannot approve actions.';
COMMENT ON TABLE graph_snapshots IS 'Versioned simulated input, prediction and realized-label exports; no trained model.';
