# Milestone 2 implementation plan and audit

The existing milestone has a Spring Boot authoritative 0.1 s engine, directed Chennai routing, PostgreSQL state/events/scenarios, a MapLibre dashboard, and executed tests. Historical research cohorts and OSM provenance are separate. There is no trained ML model or operational graph. Existing scripts, datasets, API routes, tests and milestone evidence will be preserved.

Implement simulated warehouses/docks/drivers/deliveries and explicit assignments, with deterministic dock service/queues and driver constraints. Resource definitions join saved scenario configurations; runtime operational state joins existing transactional checkpoints. Legacy unassigned trucks retain milestone 1 behavior.

Build a separate JGraphT directed heterogeneous operational graph. Edge meanings and validity derive only from explicit assignments and computed schedule conflicts. Propagate rule-based risk by bounded maximum-product paths per cause, then combine distinct causes; cycles cannot amplify one cause. Predicted consequences and realized queue/duty/deadline outcomes are separate.

Add typed AI extension interfaces and backend-validated, operator-approved orchestration contracts. Export versioned feature schemas and realized simulated labels for future HeteroData conversion. No trained GNN, external paid AI dependency or autonomous LLM agent is included.

Extend the dashboard with manual resources, assignments, map facilities, dependency graph/risk inspection and consequence timeline. Run old and new Java/Python/frontend tests, actual API/PostGIS/persistence/replay checks and browser workflows. Document graph semantics, AI boundaries, training limitations and results. Stop after milestone 2.
