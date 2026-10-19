# Optional Maven Central relay for this development host

Docker containers on this host could not reach Maven Central: direct outbound HTTPS failed even though a Python HTTPS request on the Windows host succeeded. The relay lets Docker obtain build dependencies through the host. Standard installations can continue using Maven Central directly.

The helper accepts only plain `/maven2/` artifact paths and fetches from `https://repo.maven.apache.org`. It rejects generic proxy requests, external redirects, queries, encoded path tricks and traversal. It stores original artifact bytes under the fixed `.cache/maven-central/` directory, alongside upstream URLs, timestamps, byte counts and SHA-256 digests. Every cached response is verified before use. GET and HEAD are supported. Downloads are bounded to 128 MiB per artifact. Transient network/server failures receive up to two retries with backoff; genuine 404 responses are preserved, and longer upstream cooldowns are not bypassed. No research datasets or acquisition manifests are changed.

Run in a separate PowerShell terminal from the repository root:

```powershell
python scripts/maven_central_relay.py --bind 0.0.0.0 --port 18089
```

Docker Desktop reaches this relay at `http://host.docker.internal:18089/maven2`. The explicit `--bind` allows access from Docker; the helper otherwise defaults to loopback. Stop it with Ctrl+C after the build. The cache remains reusable. Add `.cache/` to `.gitignore` so downloaded build artifacts stay local.

When the simulator backend Dockerfile supports `MAVEN_MIRROR_URL`, build with:

```powershell
docker build --build-arg MAVEN_MIRROR_URL=http://host.docker.internal:18089/maven2 -t cascadeshield-simulator-backend simulator/backend
```

The simulator startup documentation supplies the applicable Compose command. This mirror is needed only during dependency resolution; the running simulator does not use it.

For a standalone Maven test run, write a temporary Maven settings file containing:

```xml
<settings>
  <mirrors>
    <mirror>
      <id>host-maven-central</id>
      <mirrorOf>central</mirrorOf>
      <url>http://host.docker.internal:18089/maven2</url>
    </mirror>
  </mirrors>
</settings>
```

Mount this file into the Maven container and pass `mvn -s /path/settings.xml`. The real geographic routing test is enabled by `-Dcascade.test.graph=/path/road_graph.json`; bind the prepared graph into the test container. `RoadGraphTest` uses three explicitly TESTONLY routing fixtures plus a separate test against the real Chennai snapshot.
