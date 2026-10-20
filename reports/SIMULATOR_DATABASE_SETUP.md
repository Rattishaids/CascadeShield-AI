# Portable simulator database setup

The release uses the root `compose.yaml` and an isolated PostgreSQL/PostGIS volume. Simulator tables live in `cascadeshield_sim`; backend startup applies Flyway migrations and loads the included Chennai network. The original research database and its historical imports are separate and are not required for the release application.

## Start the database

Start Docker Desktop with Linux containers, then run from the extracted repository root in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_database.ps1
```

When `.env` is absent, the helper calls portable setup with `-SkipBuild`, generates a random local password, and validates the included graph. It starts only the database, waits for its health check, and queries the actual PostgreSQL/PostGIS versions. It preserves an existing configuration, database volume and records. No host Python environment, dependency installation or historical import is performed. Start the UI and backend separately:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_simulator.ps1
```

For an existing alternate configuration, use the same file for both helpers:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_database.ps1 -EnvFile .env.demo
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -EnvFile .env.demo
```

Use `scripts/setup.ps1` first with the desired project name and ports when generating a new alternate configuration. Settings are read literally from the selected private env file. Conflicting shell environment values are rejected so Compose and the helper address the same instance. Keep this file private and preserve it with its database volume; initialization credentials apply only when that volume is empty. The root README documents configuration and startup in detail.

## Backend connection and persistence

Compose supplies the backend JDBC URL `jdbc:postgresql://database:5432/<POSTGRES_DB>` and its private credentials from the selected env file. Host database clients use `127.0.0.1` and that file's `POSTGRES_PORT`; the generated default port is `55433`. Read the actual database/user settings from the private file. No password is published or printed by the helper.

The default Compose project is `cascadeshield-demo`; its persistent volume is `cascadeshield-demo_demo_database`. An alternate project receives a separately prefixed volume. Host ports bind to `127.0.0.1`. The original research project and its volume are not referenced by the portable Compose application.

Stop and resume without deleting the selected project's records:

```powershell
docker compose --env-file .env -f compose.yaml stop database
docker compose --env-file .env -f compose.yaml start database
```

Use `scripts/stop_simulator.ps1` to stop the whole app. Avoid `down -v` when retaining data. `restart: unless-stopped` resumes services after Docker restarts unless they were explicitly stopped.

## Historical Milestone 1 import evidence

The following evidence describes the original research workspace, not imports performed by the portable helper. Historical raw/processed cohorts, the research database and some detailed execution files remain outside the release ZIP. These statements preserve the original executed results; they are not instructions to recreate those imports from an incomplete curated package.


The Docker engine was unavailable during the original acquisition run; that earlier historical report, `reports/database_execution.json`, is retained unchanged. In the simulator setup session Docker Desktop was started successfully and an actual database was used. New verification results are saved in `reports/simulator_database_execution.json` after the loader commits.

Validation checks every eligible processed table against `processed_manifest.json`, its row count and stored raw/processed SHA-256 provenance; evaluates every typed view; checks available geometries for validity and EPSG:4326; and refuses Porto/NYC quarantined assets or unexpected research imports. Invalid/missing source coordinates remain NULL geometry and are reported.

The completed import and an idempotent second setup both passed: **18 tables, 2,414,128 rows**, zero invalid geometries, and zero wrong SRIDs. The Cambridge sites table preserves one NULL geometry from its source coordinate issue. The second setup recreated the same-image container after pinning the image digest; all records survived in the named volume, and all raw/processed checksums were reverified by the existing loader. Full typed-expression scans passed, including all 100,927 collision timestamps and 8,784 weather timestamps.

The tested Docker image is pinned to `postgis/postgis:17-3.5@sha256:01a6a70e41e6c4467c8f55f6063555ed72db2d6662cd0d571040d42eadaeb6f6`. Its observed versions are PostgreSQL **17.5** and PostGIS **3.5.2**. The PostGIS project's [Docker image documentation](https://github.com/postgis/docker-postgis) documents the PostgreSQL 17 volume path and initialized extensions used here.

Database roles, migrations, and real network loading are implementation infrastructure. Importing historical GB/Brazil/Birmingham/England and Wales cohorts does not make them observations of Chennai logistics. The demo routes use real Chennai geographic data and its vehicle operations and incidents are explicitly simulated.

## Release integration verification

Run integration checks only against a disposable release installation. They reset simulated state, create test records and, for selected suites, restart its backend. Do not run them during an operator demonstration or point them at the preserved research database.

After starting that isolated app and installing the optional `requirements-release-test.txt` dependencies in an isolated Python environment:

```powershell
python scripts/test_release_integration.py --suite simulator --env-file .env --report .runtime/simulator-integration.json --allow-reset
python scripts/test_release_integration.py --suite operations --env-file .env --report .runtime/operations-integration.json --allow-reset
python scripts/test_release_integration.py --suite benchmark --env-file .env --report .runtime/benchmark-integration.json --allow-reset
```

The adapter reads credentials privately from the selected env file, verifies that the API and database identify the same checkpoint, and refuses targets containing the historical research import metadata. It tests actual HTTP commands, PostGIS, persistence/replay and backend restart without inventing legacy scenarios. Current executed results and their scope are in [RELEASE_VERIFICATION.md](RELEASE_VERIFICATION.md).

The original Milestone 1 integration run passed **15 checks**. A separate actual backend restart preserved **17.3 simulated seconds**, three mid-route vehicles, one incident, a saved scenario and five audit events. Those historical results describe their original test run. The underlying research-oriented test scripts now require an explicit private `DATABASE_URL` or their documented `--dsn` setting; use the release adapter above for fresh portable databases.
