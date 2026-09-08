# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.2] - 2026-09-08

### Added

- Portable `.env` loading next to `hostit_dns.py` (no hardcoded server paths, no `python-dotenv`)
- `exists` CLI command to check a specific DNS record
- Idempotent `create_record` (skips POST when an identical record already exists)
- Generic Certbot auth/cleanup hooks for native and Docker usage
- `Dockerfile.certbot` with `requests` for Certbot DNS-01 in containers
- Expanded README covering CLI, native Certbot, and Docker Compose examples

### Changed

- `HostItDNSClient()` can load credentials from the environment with no constructor args
- Certbot hooks default to production Host.it SSO/API endpoints via the shared client
- Cleanup deletes only the matching TXT challenge value, leaving other values on the same name
- `.env.example` and `.gitignore` made environment-agnostic

### Removed

- Hardcoded `/srv/dns_updater` env path and test SSO defaults from Certbot hooks

## [0.0.1] - 2026-09-08

### Added

- Initial Host.it DNS API client (`hostit_dns.py`) with SSO auth and zone CRUD
- CLI commands: `get`, `create`, `delete`, `test`
- Certbot authenticator and cleanup hook scripts
- `.env.example`, `.gitignore`, and `requirements.txt`
- Basic project README

[0.0.2]: https://github.com/larss/hostit-dns-api/releases/tag/v0.0.2
[0.0.1]: https://github.com/larss/hostit-dns-api/releases/tag/v0.0.1
