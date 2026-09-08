# Version Bump Procedure (hostit-dns-api)

Use this checklist for each release version bump.

## 1) Choose Version

Follow semver:

- `MAJOR`: breaking changes (CLI/API contract, env var names, Certbot hook behavior)
- `MINOR`: new backward-compatible features (commands, hooks, Docker helpers)
- `PATCH`: backward-compatible fixes and small improvements

## 2) Prepare Changelog Content

Before bumping the version number, scan changes since the last changelog entry:

1. Read `CHANGELOG.md` and note the last released version/date.
2. Review git changes since that release.
3. Check high-impact areas:
   - `hostit_dns.py`
   - `certbot_authenticator.py`, `certbot_cleanup.py`
   - `Dockerfile.certbot`, `README.md`, `.env.example`
4. Categorize user-facing changes: `Added`, `Fixed`, `Changed`, `Removed`.
5. Do **not** document the version bump itself in changelog bullets.

If work is still in `## [Unreleased]`, rename that section to `## [X.Y.Z] - YYYY-MM-DD` instead of duplicating content.

## 3) Update Versions In Required Files


| File           | Field / content | Action                                                        |
| -------------- | --------------- | ------------------------------------------------------------- |
| `CHANGELOG.md` | top entry       | `## [X.Y.Z] - YYYY-MM-DD` (first section after `# Changelog`) |
| `VERSION`      | file body       | `X.Y.Z` (single line, no `v` prefix)                          |
| `hostit_dns.py`| `__version__`   | `"X.Y.Z"`                                                     |


## 4) Write Changelog Sections

Use as needed:

- `### Added`
- `### Fixed`
- `### Changed`
- `### Removed`

Keep bullets concrete and user-facing (CLI, Certbot, Docker, env configuration).

## 5) Quick Verification

- [ ] `CHANGELOG.md` top entry is `## [X.Y.Z] - YYYY-MM-DD`
- [ ] No stale `## [Unreleased]` section left above the new release
- [ ] `VERSION` contains `X.Y.Z`
- [ ] `hostit_dns.py` → `__version__ = "X.Y.Z"`
- [ ] Date format is `YYYY-MM-DD`
- [ ] Major features from the release are not missing from the changelog

Optional check:

```bash
rg '__version__|^## \[' VERSION CHANGELOG.md hostit_dns.py
```

## 6) Suggested Commit Message

One concise line with 1–3 highlights:

```
release: vX.Y.Z - add <feature>, fix <bug>, change <behavior>
```

Example:

```
release: v0.0.2 - portable env loading, idempotent DNS create, Certbot Docker image
```
