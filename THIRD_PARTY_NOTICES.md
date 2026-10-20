# Third-party components and data

The included Chennai road database is derived from **OpenStreetMap contributors** and is distributed under ODbL 1.0. Read [DATA_LICENSES.md](DATA_LICENSES.md) and the included [ODbL text](LICENSES/ODbL-1.0.txt). Geographic data licensing is separate from software licensing.

The application uses the following upstream projects. Setup downloads their packages or container images; this Git repository does not vendor their installations. Their own licenses, notices and dependency terms continue to apply. Consult the installed dependency distributions and the linked upstream repositories for complete notices, including transitive dependencies.

| Component | Upstream |
| --- | --- |
| React | https://github.com/facebook/react |
| TypeScript | https://github.com/microsoft/TypeScript |
| Vite and Vitest | https://github.com/vitejs/vite ; https://github.com/vitest-dev/vitest |
| MapLibre GL JS | https://github.com/maplibre/maplibre-gl-js |
| Lucide | https://github.com/lucide-icons/lucide |
| Spring Boot | https://github.com/spring-projects/spring-boot |
| JGraphT | https://github.com/jgrapht/jgrapht |
| Flyway | https://github.com/flyway/flyway |
| PostgreSQL JDBC | https://github.com/pgjdbc/pgjdbc |
| PostgreSQL and PostGIS | https://www.postgresql.org/about/licence/ ; https://postgis.net |
| Eclipse Temurin, Maven, Node.js, Nginx and Python container images | https://hub.docker.com/_/eclipse-temurin ; https://hub.docker.com/_/maven ; https://hub.docker.com/_/node ; https://hub.docker.com/_/nginx ; https://hub.docker.com/_/python |
| Optional PyTorch and PyTorch Geometric | https://github.com/pytorch/pytorch ; https://github.com/pyg-team/pytorch_geometric |
| Optional XGBoost, NumPy and scikit-learn | https://github.com/dmlc/xgboost ; https://github.com/numpy/numpy ; https://github.com/scikit-learn/scikit-learn |
| Optional Playwright and psycopg test tooling | https://github.com/microsoft/playwright-python ; https://github.com/psycopg/psycopg |

Frontend dependency versions are resolved by `simulator/frontend/package-lock.json`. Backend versions are resolved from `simulator/backend/pom.xml` and its Spring Boot parent. Optional inference package versions are recorded in `requirements-ml-cpu.txt` and `ml/Dockerfile`. Image tags and the pinned PostGIS digest are in `compose.yaml` and the Dockerfiles.

No project-wide license grant for the original CascadeShield software or trained model parameters has been selected. Public repository access alone does not grant unrestricted reuse rights. This notice does not replace upstream licenses or grant rights the project does not own. The ODbL terms for the included geographic database remain explicit.
