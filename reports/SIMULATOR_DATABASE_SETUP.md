# Simulator database setup

The first simulator milestone uses a local Docker PostgreSQL/PostGIS database. Existing research datasets stay in their original region/year schemas; Chennai simulated operations use the separate `cascadeshield_sim` schema managed by the simulator's Flyway migrations. No ML model is trained by these commands.

## Start and verify

From the repository root in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_database.ps1
```

This starts Docker Desktop hidden if its Linux engine is unavailable, starts the persistent PostGIS service, installs `requirements-db.txt` in `.venv`, invokes the existing checksum-verified loader, and runs real database validation. Repeating it verifies existing imports without replacing records. `-SkipDependencyInstall` skips pip; `-SkipImport` verifies the existing imports without invoking the loader. A missing import still fails verification.

For Docker already running, the equivalent infrastructure command is:

```powershell
docker compose -f infrastructure/compose.yaml up -d --wait database
$env:DATABASE_URL = 'postgresql://cascadeshield:cascadeshield@127.0.0.1:55432/cascadeshield'
& .\.venv\Scripts\python.exe scripts/load_postgis.py --execute
& .\.venv\Scripts\python.exe scripts/verify_database.py
```

The included credentials are local demonstration defaults. The host port binds only `127.0.0.1`. Optional local changes belong in `infrastructure/.env` copied from `.env.example`; PostgreSQL initialization credentials apply only when its named volume is empty. If `DATABASE_URL` is already set, the setup script uses it for loader and validation, so it must refer to the intended database.

## Backend connection

| Location | JDBC URL | User | Local demo password |
| --- | --- | --- | --- |
| Backend running on host | `jdbc:postgresql://127.0.0.1:55432/cascadeshield` | `cascadeshield` | `cascadeshield` |
| Backend on `cascadeshield_default` Docker network | `jdbc:postgresql://database:5432/cascadeshield` | `cascadeshield` | `cascadeshield` |

Compose project: `cascadeshield`; service: `database`; container: `cascadeshield-database-1`; persistent volume: `cascadeshield_database_data`. A separate Compose application can declare `cascadeshield_default` as an external network.

## Stop and resume

```powershell
docker compose -f infrastructure/compose.yaml stop database
docker compose -f infrastructure/compose.yaml start database
```

These commands preserve database records. `restart: unless-stopped` restarts the database when Docker restarts unless it was explicitly stopped. No service is installed outside Docker and no global database configuration is changed.

## Evidence

The Docker engine was unavailable during the original acquisition run; that earlier historical report, `reports/database_execution.json`, is retained unchanged. In the simulator setup session Docker Desktop was started successfully and an actual database was used. New verification results are saved in `reports/simulator_database_execution.json` after the loader commits.

Validation checks every eligible processed table against `processed_manifest.json`, its row count and stored raw/processed SHA-256 provenance; evaluates every typed view; checks available geometries for validity and EPSG:4326; and refuses Porto/NYC quarantined assets or unexpected research imports. Invalid/missing source coordinates remain NULL geometry and are reported.

The completed import and an idempotent second setup both passed: **18 tables, 2,414,128 rows**, zero invalid geometries, and zero wrong SRIDs. The Cambridge sites table preserves one NULL geometry from its source coordinate issue. The second setup recreated the same-image container after pinning the image digest; all records survived in the named volume, and all raw/processed checksums were reverified by the existing loader. Full typed-expression scans passed, including all 100,927 collision timestamps and 8,784 weather timestamps.

The tested Docker image is pinned to `postgis/postgis:17-3.5@sha256:01a6a70e41e6c4467c8f55f6063555ed72db2d6662cd0d571040d42eadaeb6f6`. Its observed versions are PostgreSQL **17.5** and PostGIS **3.5.2**. The PostGIS project's [Docker image documentation](https://github.com/postgis/docker-postgis) documents the PostgreSQL 17 volume path and initialized extensions used here.

Database roles, migrations, and real network loading are implementation infrastructure. Importing historical GB/Brazil/Birmingham/England and Wales cohorts does not make them observations of Chennai logistics. The demo routes use real Chennai geographic data and its vehicle operations and incidents are explicitly simulated.

## Simulator integration verification

After the backend is running at `http://127.0.0.1:8080`, run:

```powershell
& .\.venv\Scripts\python.exe scripts/test_simulator_integration.py
```

This exercises actual HTTP commands and reads PostgreSQL to verify routing, motion, incident effects, manual decisions, checkpoint persistence, realized KPIs, and saved-scenario replay. It resets the local simulated fleet and creates three test trucks; historical research imports are checked before and after and remain untouched. It leaves a saved integration scenario and the completed replayed test fleet. Its test evidence is written to `reports/simulator_integration_tests.json`. That file is created only by an actual run and reports failures explicitly.

The actual first API run passed **15 checks**, including exact replay of the saved vehicle/incident/KPI snapshot and preservation of all 18 research imports. An additional real backend-container restart passed: **paused clock 17.3 seconds**, three mid-route vehicles, one active incident, one saved scenario, and five audit events survived. The recovered paused clock stayed frozen. This independent restart evidence is in `reports/simulator_restart_tests.json`.

To include the restart check with the full integration run, use `--test-restart`. To rerun only restart persistence against an existing tested fleet and keep the full integration report separate:

```powershell
& .\.venv\Scripts\python.exe scripts/test_simulator_integration.py --restart-only --report reports/simulator_restart_tests.json
```

The restart check resets the simulated fleet to its initial assignments, steps to a paused checkpoint, injects a simulated slowdown, and restarts only the backend container. It leaves the recovered fleet paused for inspection; the database container and historical records remain running and intact.
