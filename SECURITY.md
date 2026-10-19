# Security policy

## Reporting a vulnerability

**Please do not open a public issue for security problems.** Use GitHub's private reporting: *Security → Report a vulnerability* on this repository ([direct link](https://github.com/ECG-Rudy-Glt/COACH/security/advisories/new)). Include the version/commit, what you did, what you expected, what happened, and (if possible) a minimal proof of concept.

You can expect an acknowledgement within 7 days and a status update within 30 days. We will credit you in the release notes unless you prefer otherwise. Please give us reasonable time to ship a fix before disclosure.

## Scope

In scope: the application code, the Docker/Compose configuration and documentation in this repository (authentication, session handling, access control between users, injection, SSRF, secret handling, prompt-injection that crosses a safety boundary, container hardening).

Out of scope: vulnerabilities in third-party services (LLM providers, Garmin), issues requiring a compromised host or admin, missing hardening on instances you operate in ways the docs advise against, denial of service by sheer volume, reports from automated scanners without a demonstrated impact.

## Supported versions

Only the latest release and `main` receive security fixes while the project is pre-1.0.

## Hardening your own install

See [docs/security.md](docs/security.md) and [docs/exposure.md](docs/exposure.md).
