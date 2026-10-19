# First simulator milestone: repository audit and implementation plan

## Audit

The repository contains a complete bounded acquisition pipeline, 12 original raw files, 18 processed CSVs, data-quality/licensing/provenance reports, and generated PostgreSQL/PostGIS imports. There are no existing application services, Java/React projects, trained ML models, conference-paper PDFs, or dataset-strategy PDFs. Previous database reports record no executed import. The current environment has Python, Node/npm and Docker, but no Java/Maven/PostgreSQL binaries on PATH and no configured DATABASE_URL.

Existing data, scripts, tests, manifests and historical reports are preserved. Porto and NYC remain quarantined. GB accidents, Cambridge sites, Brazil e-commerce and Birmingham weather are not joined to simulated Chennai operations. Eligible historical datasets remain separate research schemas.

## Ordered implementation

1. Start a local PostgreSQL/PostGIS service, import eligible datasets with the existing loader, and execute database checks. Keep the DB bound to localhost. Add migrations for a separate simulator schema.
2. Acquire a bounded real OSM Chennai road extract with immutable originals and separate provenance. Prepare directed road edges with shared real OSM nodes, access/one-way filtering and turn restrictions. Any missing speed values receive explicitly documented simulation assumptions, not invented observations.
3. Add a Spring Boot backend with typed REST commands, a directed routing service, a deterministic fixed-step simulation engine, a labelled rule-based wait/reroute recommendation interface, structured events, actual simulated KPIs, PostGIS road persistence, current-state checkpoints and saved scenario replay.
4. Add a React/TypeScript/Vite/MapLibre dashboard that renders backend positions, sends operator commands, permits manual truck creation, road incident injection and intervention approval, and exposes scenario save/replay.
5. Test connected road movement, inaccessible routes, pause/resume/speed controls, closure/slowdown impact, finite bounded rule-based risk, non-teleporting approved interventions, reproducible replay, persisted state and consistent KPIs. Execute an actual browser demonstration and document launch commands.

## Backend boundaries

Road routing is separate from future operational dependencies. Simulation state is authoritative in the backend. Prediction and prevention interfaces can later receive a trained model and a dependency-aware optimizer. The first milestone estimates direct travel impact only; it does not claim cascade prediction, learned probabilities, field outcomes, calibrated risk, optimized dock/driver scheduling, or research-paper performance.

## Scope

Implement the complete first vertical slice only. Trucks, their assignments, incidents and outcomes are labelled SIMULATED. Map geometry is REAL OSM geography. Risk and action scoring are RULE-BASED ESTIMATES. Historical research data stays distinct. Dependencies/docks/driver-law scheduling, ML/FastAPI/XGBoost, OR-Tools optimization, cascade experiments and blockchain integration remain later milestones.
