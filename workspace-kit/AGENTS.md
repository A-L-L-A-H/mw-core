# AGENTS.md — MoonWitness Workspace

Satu-satunya instruksi agen untuk seluruh workspace `/repo`. Jangan buat AGENTS.md, CLAUDE.md, atau aturan agen lain di dalam folder repo individual.

## Workspace

- Manifest kanonik: [`workspace.json`](workspace.json). Ini sumber kebenaran untuk branch, remote, port, dan profile.
- Overview + aturan README/CI: [`README.md`](README.md).
- Satu-satunya folder rencana/task: [`.plan/`](.plan/). Dilarang membuat `.plan/` di dalam repo project atau worktree.
- Tool orchestrator: `./mw-ws.sh status|pull|sync|test|ci|health|doctor|drift|lint` (atau `.\mw-ws.ps1`).
- Cek konsistensi: `./mw-ws.sh drift` — harus "No drift" sebelum menyerahkan pekerjaan.

## Aturan utama

1. **Satu workspace, satu aturan.** File ini mengikat semua repo di bawah `/repo`.
2. **Satu `.plan/`.** Semua rencana, task, proof, dan artifacts masuk ke `/repo/.plan/<nama>/`. Tidak boleh ada `.plan/` di `mw-*/` atau worktree.
3. **Satu README standar.** Tiap repo memakai: What it does / Quick start / Verify / Configuration / Notes. Perintah harus cocok dengan manifest (`package.json`, `Cargo.toml`, `go.mod`, `pyproject.toml`).
4. **Manifest dulu.** Perubahan branch, port, atau repo baru harus masuk ke `workspace.json` dan README root di commit yang sama.
5. **Tidak ada agent config di project.** Dilarang: `AGENTS.md`, `CLAUDE.md`, `.agents/`, `.claude/`, `.qoder/`, `.swarm/`, `.system_generated/`, `.cursorrules`, `.windsurfrules` di dalam folder repo. Yang boleh tetap ada: `.github/` untuk CI/workflow dan `.env.example`.
6. **Tidak ada folder docs di project.** Dilarang `docs/`, `doc/`, `documentation/` di dalam repo manapun pada kedalaman berapapun. Satu-satunya tempat dokumentasi panjang adalah repo [`mw-docs`](mw-docs/) (auto-deploy ke Cloudflare Pages). README repo cukup singkat dan boleh menautkan ke `mw-docs`.
7. **Dilarang commit binaries.** Dilarang men-commit file biner hasil kompilasi (`*.exe`, `*.dll`, `*.so`, dsb). Binaries dirilis via GitHub Releases atau package registry, bukan di git tree.
8. **Worktree lifecycle.** Worktree sementara harus dibersihkan setelah selesai (`git worktree prune`). Jangan biarkan worktree terbengkalai di repo project.
9. **Higienitas wajib.** Tiap repo punya `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `.env.example`, `.gitignore`, dan CI per stack.
10. **Lockfile policy.** Setiap repo wajib commit lockfile sesuai stack (`go.sum`, `Cargo.lock`, `bun.lock`, atau `package-lock.json`). Tidak boleh ada lockfile yang di-ignore.
11. **Commit konvensional.** `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `perf:`, `build:`, `ci:`, `revert:`, `security:`, `deps:`, `style:`, `release:`. Validasi otomatis di CI PR.
12. **CI template per stack.** Semua CI repo di-generate dari `.github/workflow-templates/ci-<stack>.yml`. Harus menyertakan: commitlint, frozen lockfile install, lint/typecheck, test dengan coverage threshold.
13. **Tidak ada push / PR / merge tanpa permintaan eksplisit.** CI wajib hijau; PR gagal tidak boleh di-merge paksa.
14. **Perubahan lintas repo** dibuat di branch dengan nama deskriptif, satu commit per repo atau per kelompok yang koheren, lalu diverifikasi dengan `./mw-ws.sh drift`.
15. **Global Code Quality & Complexity Budgets.** Kebijakan kualitas lintas-bahasa didefinisikan di [`quality-policy.json`](quality-policy.json) (`maxFileLines: 400`, `maxTestFileLines: 800`, `maxLineLength: 120`, `maxFunctionLines: 60`, `maxCyclomaticComplexity: 12`, `maxNestingDepth: 4`, `maxParams: 5`, `maxDirSourceFiles: 30`, serta larangan marker `TODO`/`FIXME`/`HACK`/`XXX`/`@ts-ignore` di kode produksi). Jalankan `./mw-ws.sh lint` atau `.\mw-ws.ps1 lint` (mendukung `--repo`, `--changed`, `--strict`, `--json`, `--summary`) untuk memverifikasi kepatuhan.
16. **Standardisasi Folder `scripts/`.** Seluruh repo wajib mengikuti struktur, bahasa, penamaan, dan batas jumlah skrip sesuai `scriptsPolicy` di [`quality-policy.json`](quality-policy.json):
    - **5 Subdirektori Kanonik** (wajib jika repo memiliki `> 5` skrip; struktur datar `scripts/*.ext` hanya diizinkan jika `<= 5`):
      - `scripts/ci/`: pemeriksaan read-only, validator, audit statis/keamanan (`check-*`, `validate-*`, `audit-*`)
      - `scripts/build/`: build guard, codegen, compiler aset (`build-*`, `generate-*`)
      - `scripts/release/`: packaging, signing, SBOM/attestation (`release-*`, `publish-*`)
      - `scripts/ops/`: deploy, backup, DR, install, cleanup, cron (`deploy-*`, `backup-*`, `dr-*`, `install-*`, `cleanup-*`, `register-*`; operasi destruktif WAJIB mendukung `--dry-run`)
      - `scripts/dev/`: helper dev lokal, autofix, seeder, scaffolding (`dev-*`, `seed-*`, `create-*`, `run-*`)
      - Opsional `scripts/lib/`: HANYA untuk modul helper bersama yang di-import oleh 2+ skrip.
    - **Standar Bahasa**: logika lintas-platform -> `.mjs` (Node/Bun ESM; root workspace `z:\repo\scripts\` memakai Python 3 stdlib); shell POSIX/VPS/hook -> `.sh` (`#!/usr/bin/env bash` + `set -euo pipefail`); host Windows-only -> `.ps1` (`Set-StrictMode -Version Latest`). Dilarang: `.cjs`, `.bat`, `.cmd`, biner terkompilasi, serta nama scratch (`try*`, `tmp*`, `analyze*`, `compare*`, `fix_*`).
    - **Penamaan & Budget**: wajib `kebab-case` `<verb>-<target>.<ext>`; batas maksimal `10` skrip (repo standar), `25` (repo ops seperti `mw-stack`), `40` (monorepo seperti `mw-xv`).

## Kepemilikan & batas aman

| Surface | Aturan |
|---|---|
| `workspace.json`, `README.md`, `mw-ws.*`, `scripts/drift.py`, `.plan/`, `AGENTS.md` | Root workspace — otoritatif |
| `mw-docs/` | Documentation hub — auto-deploy Cloudflare Pages; tidak ada docs di repo lain |
| `.github/workflows/*`, `scripts/ci/*` di repo | CI milik repo masing-masing; jangan hapus saat membersihkan config agent |
| `packages/orm/src/services.ts`, `apps/api/src/commands/*`, `apps/api/src/lifecycle/*` di `mw-xv` | D12 isolation — jangan disentuh tanpa izin owner |
| `.githooks/*`, workflow promote/release/sync, `scripts/release-*.mjs`, `scripts/sync-main-to-dev.mjs`, `.github/CODEOWNERS` | Protected — butuh persetujuan owner |
| Variabel `AUTONOMOUS_PROMOTE`, `AUTONOMOUS_STABLE_RELEASE`, `AUTO_HEAL_RETRY`, `AUTOMATION_APP_CLIENT_ID` | Governance — jangan diubah agen |

## Catatan migrasi

Aturan ini menggantikan `mw-xv/AGENTS.md` dan `mw-xv/apps/board/AGENTS.md`. Arsip lama dan submigrasi berada di [`.scratch-archive/`](.scratch-archive/) dan [`.plan/mw-xv/`](.plan/mw-xv/).
