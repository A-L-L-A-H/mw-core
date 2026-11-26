# mw-core — MoonWitness Canonical Application-Contract / Catalog Repo

**mw-core** is the canonical registry and contract catalog for the MoonWitness sovereign fleet. It does **not** contain installers, CLI, Docker Compose, Caddy, cloudflared, k8s, Docker runtime files, or provisioner scripts — those are owned by **mw-stack**.

## Purpose

This repo provides:
- A **service registry** (`registry/services.json`) listing every MoonWitness service, its contract endpoints, and runtime data derived from `workspace.json` and existing mw-rid contracts.
- A **repository catalog** (`registry/repositories.json`) with canonical Git metadata for all MoonWitness repositories.
- An **identity contract** (`contracts/identity.md`) derived from `mw-rid` OIDC specifications.
- A **boundary specification** (`docs/boundary.md`) defining the strict separation between mw-core and mw-stack.

## Ownership Boundary

| Surface | Owned By |
|---|---|
| `install.sh`, `docker-compose.yml`, `mwctl`, Caddy/cloudflared, k8s/, Docker runtime files, installer/provisioner scripts | **mw-stack** |
| `README.md`, `docs/boundary.md`, `registry/services.json`, `registry/repositories.json`, `contracts/identity.md`, JSON schemas | **mw-core** |

## Quick Reference

| Repo | Profile | Port | Stack | Pillar |
|---|---|---|---|---|
| mw-echo | lite | 4310 | Go | Sovereign Core Node |
| mw-rid | id | 4480 | TypeScript/Node | OIDC Identity Provider |
| mw-dock | saas | 3000 | TypeScript/Bun | SaaS Workspace & Dock |
| mw-xv | saas | 3001 | TypeScript/Bun | Board & Execution Engine |
| mw-design | saas | 8080 | TypeScript/Bun | Visual Design Studio |
| mw-mylove | portal | 4460 | TypeScript/Bun | Community & Portal |
| mw-stack | full | — | Docker/Shell | Fleet Orchestrator |
| mw-lab | ops | 4400 | Go | Fleet Operations Lab |
| mw-mission | ops | 4410 | Rust | Mission Control |
| mw-isp | isp | 8091 | Rust | ISP & RADIUS |
| mw-cp | ops | 4440 | Go | Control Plane & PaaS |
| mw-corpus | epistemic | 4420 | TypeScript/Bun | Epistemic Corpus |
| mw-nexus | epistemic | 4430 | Rust | Epistemic Nexus |
| mw-lore | epistemic | 4450 | TypeScript/Bun | Epistemic Lore |
| mw-studio | studio | 4470 | Python | Media & AI Studio |
| mw-pocket | mobile | — | Expo/React Native | Android-First Mobile Companion |
| mw-rocksoul-cli | rocksoul | — | Go | Rocksoul AI |
| mw-rocksoul-gateway | rocksoul | 4510 | Go | Rocksoul AI |
| mw-rocksoul-core | rocksoul | 4520 | TypeScript/Bun | Rocksoul AI |
| mw-rocksoul-mcp | rocksoul | 4530 | TypeScript/Bun | Rocksoul AI |
| mw-rocksoul-sandbox | rocksoul | 4540 | TypeScript/Bun | Rocksoul AI |
| mw-templates | full | — | JSON/Node | PaaS Template Catalog |
| mw-dx | rocksoul | — | Tauri/TypeScript | Rocksoul AI |

---

See `registry/services.json`, `registry/repositories.json`, `contracts/identity.md`, and `docs/boundary.md` for full details.