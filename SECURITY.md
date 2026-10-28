# Security policy

Authentication and rate limiting, untrusted-filename handling, opt-in integrations
(SMTP, webhooks, OCR, models, Postgres, Redis, Docker) and the deliberately deferred
boundary list are covered in [docs/SECURITY.md](docs/SECURITY.md), with the roadmap
in [ROADMAP.md](ROADMAP.md).

## Reporting a vulnerability

Open a [security advisory](https://github.com/FishRaposo/groundtruth/security/advisories/new)
or email fishraposo@gmail.com with the subject `[groundtruth security]`. Please do
not open a public issue for a security report.

## Supported versions

Security fixes target the latest tagged release and `main`.
