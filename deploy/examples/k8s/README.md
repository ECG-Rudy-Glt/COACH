# Kubernetes example

A minimal, **unsupported-by-default** example (namespace, Postgres StatefulSet, app Deployment + Service, daily `pg_dump` CronJob, one-off exercise import Job). Docker Compose at the repository root is the supported way to self-host.

Before applying: create the `sport-coach-secrets` Secret with `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`, `SECRETS_KEY` (Fernet key), your LLM key (`LLM_API_KEY`, or the provider-specific variable), and optionally ntfy/SMTP/VAPID values. Source them from your secret manager; never commit them. Then `kubectl apply -k deploy/examples/k8s`.

Adjust: image tag, `LLM_PROVIDER`/`LLM_MODEL`, storage classes, the Service type, and expose it as described in `docs/exposure.md`.
