# MoonWitness CI Template Library

Canonical CI workflow templates. Each repo's `.github/workflows/ci.yml` is generated from exactly one of these, keyed by `stack` in `workspace.json`.

| Template | Stack | Repos |
|---|---|---|
| `ci-go.yml` | Go | mw-echo, mw-cp, mw-lab, mw-ww, mw-rocksoul-cli, mw-rocksoul-gateway |
| `ci-rust.yml` | Rust | mw-isp, mw-mission, mw-nexus |
| `ci-bun.yml` | TypeScript/Bun | mw-corpus, mw-design, mw-dock, mw-dx, mw-lore, mw-mylove, mw-rocksoul-core, mw-rocksoul-mcp, mw-rocksoul-sandbox, mw-xv*, mw-taskos |
| `ci-expo.yml` | Expo/React Native | mw-pocket |
| `ci-python.yml` | Python | mw-studio |
| `ci-data.yml` | JSON/Shell catalogs | mw-core, mw-stack, mw-templates, mw-docs |

`mw-xv` extends `ci-bun.yml` with its existing governance/release pipelines; do not replace its workflows wholesale.

## Contract

Every generated CI job must:
1. Check conventional commit messages on pull requests.
2. Install dependencies from the committed lockfile (`--frozen-lockfile` / `npm ci` / `go mod download` / `cargo fetch --locked`).
3. Run the stack's typecheck/lint, build, and test commands from the repo manifest.
4. Enforce a coverage threshold where the stack supports it.
5. Pin toolchain versions from the repo manifest — never `latest`.

## Toolchain pins (canonical)

- Node 24 (`engines.node: 24.x`, `.nvmrc` = 24)
- Bun 1.4.5 (`packageManager: bun@1.4.5`)
- Go: version from `go.mod` via `go-version-file`
- Rust: 1.89 (`rust-version` in `Cargo.toml`, `rust-toolchain.toml`)
- Python: 3.12 (`requires-python`, `.python-version`)
