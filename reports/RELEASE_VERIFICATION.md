# Portable release verification

Status: **Verified in isolated Windows ZIP installations, in basic and CPU ML modes.** Machine-readable results and exact evidence hashes are in [RELEASE_VERIFICATION.json](RELEASE_VERIFICATION.json).

The candidate contains the simulator sources, dependency manifests, migrations, small trained model bundle and permitted Chennai geographic assets. Historical data collections, operational training corpora, raw benchmark traces, private environment settings and existing databases are excluded. Existing historical milestone numbers are preserved as archived evidence, not presented as newly executed release tests.

The initial staged Git blobs were exported to a 4,041,680-byte ZIP and extracted without `.git`, Python environments, `node_modules`, build output or local configuration. Documented PowerShell setup used project `cascadeshield-ziptest`, fresh volume `cascadeshield-ziptest_demo_database`, and ports 5174/8081/55434/8091. Both the basic simulator and optional four-model CPU service started from included assets. A second clean staged-tree export used project `cascadeshield-finalzip`, a fresh `cascadeshield-finalzip_demo_database` volume, and ports 5175/8082/55435/8092. Its complete basic/ML workflow repeated successfully after the fixes on 2026-10-19. A credential cleanup on 2026-10-20 changed five CLI/database-helper files; their exact staged bytes were copied into the same disposable extraction and verified separately. All 220 current staged runtime files match that extraction: 215 retain their earlier tested bytes, and five have the follow-up evidence below. Reports and README were finalized afterward. Normal push and remote ZIP verification are recorded separately after publication.

The table combines actual executions from those clean exports and the credential-cleanup follow-up. Java, frontend, ML and browser checks retain their earlier execution evidence; they were not rerun on 2026-10-20. The three API suites, database helper, basic startup and private-DSN guards were executed after the cleanup.

| Executed check | Actual result |
| --- | --- |
| Backend container compilation and real-network Java tests | 155 passed; zero failures, errors or skips |
| Frontend Vitest and TypeScript/production build | 59 passed; build passed, including map worker |
| Applicable Python parser/geography/conversion/statistics contracts | 26 passed; seven source-artifact tests unavailable |
| Optional CPU ML/audit contracts | 39 passed; zero failures, errors or skips |
| Simulator HTTP/PostGIS/replay/restart | 17 passed |
| Operational resources, cascade, approval guards and restart | 10 passed; original version-1 saved-scenario check unavailable |
| Persistent Benchmark Lab HTTP/export/determinism/restart | 14 passed |
| Missing private database configuration in four historical CLI harnesses | Four clean rejections before database connection |
| Full simulator / operational / Benchmark Lab browser workflows | 7 / 9 / 8 passed; no page or console errors |
| Blocked-raster local roads and deterministic fallback browser | 7 passed |
| Four-model CPU UI with blocked raster after map fix | 11 passed |
| Live four-model Java-to-CPU inference / outage / recovery | 8 / 3 / 8 passed |
| Seeded road-closure/shared-dock demonstration | Actual queue observed at 1000 s; two deliveries completed, one late by 60 s |

The initial unscoped Python artifact run failed because the excluded historical datasets were absent. Its failure remains recorded; the release-specific runner explicitly reports seven source-dependent tests unavailable rather than manufacturing data. A separate ML browser check caught a genuine readiness-indicator race: roads rendered, but the final render could be missed when raster tiles were blocked. A trailing inspection of actual rendered features fixed it; the same blocked-raster check then passed. Historical benchmark numbers and frozen model source/weights were unchanged.

The recorded original-workspace preservation check found all 86 assets unchanged, 18 historical tables retaining 2,414,128 rows, and the completed 13-truck run at 854.9 seconds. The cleanup follow-up accessed only the disposable release project. Tests mutated only the isolated release simulation.

The test used the documented optional official Maven relay because this host restricts Docker's direct Maven HTTPS. Fresh verification tools used Python 3.11 with [pinned test requirements](../requirements-release-test.txt); public Windows wheels were downloaded through a clean Python container after a slow direct transfer. A missing Windows timezone wheel was added before installation succeeded. No TLS verification was disabled. Browser binaries and public dependency/image caches may be reused; none is an undeclared application asset.

The test uses the available Windows host and Docker Linux engine. Cached public container/dependency downloads may be reused, while the application source, generated configuration and database must come from the clean export. It is not a test on a different physical computer. Linux/macOS host installation is not claimed as tested.

## Final archive execution and lifecycle

The second installation repeated all three API suites (17/10/14 checks), all three complete browser workflows (7/9/8 checks), the blocked-raster basic browser (7 checks), four-model CPU browser (11 checks), four-provider API (8 checks), real inference stop/fallback (3 checks) and recovery (8 checks). Setup, basic startup, optional CPU image build, `start_ml.ps1`, `stop_ml.ps1` and `stop_simulator.ps1` were executed. Both isolated stacks stopped cleanly and their volumes were retained.

Basic setup, startup, rule/fallback APIs and the production browser were also verified with the optional model directory temporarily unavailable in the isolated extraction: three API checks and seven browser checks passed. Original model files were restored and all 34 model/source/network integrity checks passed afterward. No original workspace files were moved or deleted.

The optional Maven relay was changed to launch detached without retaining caller pipe handles; the new helper returned to its caller and the subsequent setup/build succeeded. A private verification wrapper initially treated normal redirected Docker progress as a PowerShell error; it was corrected to check native exit codes and always restore the isolated model directory. These attempts remain documented separately from passing application checks.

Detailed original commands/timings: [execution journal](release/final-execution-journal.json). Exact current runnable-file hashes and the five changed files: [runtime integrity](release/final-runtime-integrity.json). The [earlier runtime map](release/initial-final-runtime-integrity.json) retains its original bytes and hash. The curated release manifest binds every published non-self file; `scripts/check_release.py` verifies its contents without Git metadata.

## Credential cleanup follow-up on 2026-10-20

The portable database helper now uses generated/private env settings and the root Compose application. Four historical integration CLIs require an explicitly supplied private database connection. Old local credential defaults and the obsolete historical setup instructions were removed from the release; archived import results remain labelled as historical evidence.

The actual helper started the existing disposable database and queried PostgreSQL **17.5** and PostGIS **3.5.2**. Basic startup with `-NoDemo` passed. The exact updated harnesses then passed **17 simulator, 10 operational and 14 benchmark checks**, including actual backend restarts. The fresh database still had no original version-1 scenario; that check remained unavailable. Four actual CLI invocations with `DATABASE_URL` absent rejected execution before connecting to a database. The isolated stack stopped cleanly and its volume was preserved.

See the [follow-up journal](release/security-execution-journal.json), [summary](release/security-verification-summary.json), [private-DSN checks](release/security-private-dsn-guards.json), and fresh [simulator](release/security-simulator-integration.json), [operational](release/security-operations-integration.json) and [benchmark](release/security-benchmark-integration.json) results. Earlier browser/unit/ML evidence and failure hashes remain unchanged. All 34 frozen model/source/network integrity checks passed after the cleanup; the model-bound sources, trained weights and historical benchmark outcomes were unchanged.

Representative isolated commands, run from the extracted repository:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -EnvFile .env.finaltest -ProjectName cascadeshield-finalzip -FrontendPort 5175 -BackendPort 8082 -PostgresPort 55435 -MlPort 8092 -UseMavenRelay
powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -EnvFile .env.finaltest
.venv-release-test\Scripts\python.exe scripts/test_release_integration.py --suite simulator --env-file .env.finaltest --report .runtime/final-simulator-integration.json --allow-reset
.venv-release-test\Scripts\python.exe scripts/test_release_integration.py --suite operations --env-file .env.finaltest --report .runtime/final-operations-integration.json --allow-reset
.venv-release-test\Scripts\python.exe scripts/test_release_integration.py --suite benchmark --env-file .env.finaltest --report .runtime/final-benchmark-integration.json --allow-reset
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -EnvFile .env.finaltest -WithML -UseMavenRelay
powershell -ExecutionPolicy Bypass -File scripts/start_ml.ps1 -EnvFile .env.finaltest
.venv-release-test\Scripts\python.exe scripts/test_release_ml.py --api http://127.0.0.1:8082/api --service http://127.0.0.1:8092 --report .runtime/final-ml-api.json
.venv-release-test\Scripts\python.exe scripts/test_release_browser.py --ui http://127.0.0.1:5175 --api http://127.0.0.1:8082/api --ml-url http://127.0.0.1:8092 --expect-ml on --report .runtime/final-ml-browser.json
powershell -ExecutionPolicy Bypass -File scripts/stop_ml.ps1 -EnvFile .env.finaltest
powershell -ExecutionPolicy Bypass -File scripts/stop_simulator.ps1 -EnvFile .env.finaltest
```

Use fresh report names when repeating checks. Full browser commands and exact lifecycle order are in the journal. The documented Maven relay flag was needed on this test host; ordinary unrestricted HTTPS setup does not require it. No second physical computer, clean OS installation, Linux/macOS host, Windows ARM host or production deployment was verified. Cached public downloads and the host Chromium test-tool cache may be reused; no ignored application assets, old model environment or existing research database were required.
