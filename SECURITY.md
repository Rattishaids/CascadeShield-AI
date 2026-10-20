# Security and local demonstration boundary

CascadeShield AI is a research simulator for a developer workstation. Its
operator approval checks validate simulation commands; they are not user
authentication or authorization for a public service. The API, dashboard and
optional ML service should be reachable only by trusted local users.

Keep Docker's published database/backend/frontend ports bound to loopback.
The optional ML service must communicate with the backend over the configured
private Docker network or a deliberately configured local host connection.
Do not expose the application, database or unauthenticated inference endpoint
directly to the Internet. Production identity, TLS, tenant isolation and public
service hardening are outside this research release.

## Local configuration

Use the documented setup script and `.env.example` to create ignored local
configuration. Choose local database credentials during setup and retain them
outside version control. A ZIP installation must use its own Compose project
and database volume; it must not connect automatically to a developer's
existing research database.

Never commit `.env`, GitHub tokens, Kaggle credentials, private certificates,
database dumps, personal connection strings or captured authentication headers.
The repository ignore rules are a safeguard, not a secret scanner or a way to
remove information already committed. Inspect the staged files before pushing.

The included model bundle is checksum-validated against its manifest and
inference implementation. PyTorch inference loads the bundled state dictionaries
with `weights_only=True`. Load only artifacts whose origin and checksum you trust.
Inference does not gain permission to approve or mutate a simulation.

## Reporting a problem

For a possible security issue, use the repository's private vulnerability
reporting feature if it is enabled. Otherwise contact the repository owner
through an available private channel. Do not publish working credentials,
personal information or a destructive proof of concept in a public issue.

If a credential is exposed, revoke or rotate it first, then coordinate any
required history remediation with the owner. Removing a file in a later commit
does not revoke a leaked credential or remove it from earlier history.
