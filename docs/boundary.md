# mw-core Boundary Specification

This document defines the strict operational boundary between **mw-core** and **mw-stack**.

## mw-core — Canonical Application-Contract / Catalog Repo

**Owns:**
- `README.md` — high-level catalog and boundary spec
- `docs/boundary.md` — detailed boundary specification
- `registry/services.json` — service registry with real data
- `registry/repositories.json` — repository catalog with real data
- `contracts/identity.md` — identity/OIDC contract derived from mw-rid
- JSON schema files for registry validation

**Does NOT own:**
- `install.sh`, `docker-compose.yml`
- `mwctl` CLI references or installers
- Caddy/cloudflared configuration
- k8s/ manifests
- Docker runtime files
- Installer/provisioner scripts
- Fleet lifecycle docs (owned by mw-stack)

## mw-stack — Fleet Orchestrator & Installer Repo

**Owns:**
- `install.sh` — universal installer
- `install.ps1` — Windows PowerShell installer
- `docker-compose.yml` — fleet compose definition
- `mwctl` CLI binary and scripts
- `Caddyfile.template` — Caddy reverse proxy config
- `cloudflared` tunnel configuration
- `k8s/` directory
- Profiles, verification, lifecycle docs
- `.github/workflows/` CI/CD pipelines

## Boundary Enforcement

1. **No overlap**: mw-core must not contain any file that mw-stack owns (listed above).
2. **Real data only**: All registry data must be derived from `Z:\repo\workspace.json` and existing mw-rid contracts — zero mock data, zero placeholders, zero TODO, no generic `data`/`item`/`res`.
3. **JSON validation**: All `.json` files must parse cleanly.
4. **Git hygiene**: `git diff --check` and `git status --short` must pass with no forbidden surfaces.

---
*Derived from workspace.json, mw-rid contracts, and the owner's explicit governance rules.*