"""Cross-repo drift checker for the MoonWitness workspace.

Compares the checked-out state of every repository against workspace.json:
branch, remote URL, and documented service port (matched against README,
env defaults, and source literals where they can be found cheaply).

Usage: python scripts/drift.py [--json]
Exit code 0 = no drift, 1 = drift found (or missing repos when --strict).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

WS_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = WS_ROOT / "workspace.json"

# Repo name -> (source files to scan for the default port literal, port).
# A repo fails the port check only when NONE of the expected values appear.
PORT_SOURCES: dict[str, list[str]] = {
    "mw-echo": ["README.md"],
    "mw-rid": ["README.md", "apps/id/src"],
    "mw-dock": ["README.md"],
    "mw-xv": ["README.md"],
    "mw-design": ["README.md"],
    "mw-mylove": ["README.md", "src"],
    "mw-lab": ["README.md", "internal"],
    "mw-mission": ["README.md", "src"],
    "mw-isp": ["README.md", "src"],
    "mw-cp": ["README.md", "config.go"],
    "mw-corpus": ["README.md", "src"],
    "mw-nexus": ["README.md", "src"],
    "mw-lore": ["README.md", "src"],
    "mw-studio": ["README.md", "src"],
}

IGNORED_DIRS: set[str] = {"node_modules", "vendor", ".git", "target", "dist", ".next", ".turbo"}

FORBIDDEN_DOCS_DIRS: set[str] = {"docs", "doc", "documentation"}

FORBIDDEN_AGENT_CONFIGS: list[str] = [
    "AGENTS.md",
    "CLAUDE.md",
    ".agents",
    ".claude",
    ".qoder",
    ".swarm",
    ".system_generated",
    ".cursorrules",
    ".windsurfrules",
]

FORBIDDEN_BINARY_EXTS: set[str] = {".exe", ".dll", ".so", ".dylib"}

README_SECTIONS = ["What it does", "Quick start", "Verify", "Notes"]

# Manifest commands per repo (from package.json/Cargo.toml/go.mod/pyproject.toml)
MANIFEST_COMMANDS: dict[str, list[str]] = {
    "mw-corpus": ["bun install", "bun run build", "bun run start", "bun run start:dist"],
    "mw-cp": ["CGO_ENABLED=0 go build", "./control-plane", "CGO_ENABLED=0 go vet", "CGO_ENABLED=0 go test", "npm run docker:build", "npm run dev", "npm run fmt"],
    "mw-design": ["bun install", "bun run build", "bun run catalog:build", "bun run typecheck", "bun run test"],
    "mw-dock": ["bun install", "bun --filter @moonwitness/types build", "bun --filter @moonwitness/api build", "bun run start", "bun run build", "bun --filter @moonwitness/api test"],
    "mw-dx": ["bun install", "bun run typecheck", "bun test"],
    "mw-echo": [".\\start-mw-echo.ps1", ".\\start-mw-echo.ps1 -Rebuild", "go build ./...", "go test ./..."],
    "mw-isp": ["cp config.example.toml config.toml", "cargo run", "cargo check", "cargo test", "cargo build --release"],
    "mw-lab": ["CGO_ENABLED=0 go run ./cmd/mw-lab", "CGO_ENABLED=0 go build ./...", "CGO_ENABLED=0 go test ./..."],
    "mw-lore": ["bun install", "bun run start", "bun test", "bun run typecheck"],
    "mw-mission": ["cargo run --release", "cargo test", "cargo build"],
    "mw-mylove": ["bun install", "bun run start", "bun test", "bun run typecheck"],
    "mw-nexus": ["cargo run", "cargo test", "cargo build"],
    "mw-pocket": ["bun install", "bun run android", "bun run typecheck", "bun test", "bun run start", "bun run assets:generate"],
    "mw-rid": ["npm install", "npm run build", "npm run start", "npm test"],
    "mw-rocksoul-cli": ["CGO_ENABLED=0 go build -o bin/rocksoul ./cmd/rocksoul", "./bin/rocksoul", "go vet ./...", "go test -count=1 ./...", "bun test plugins/opencode-rocksoul/tests/plugin.test.ts"],
    "mw-rocksoul-core": ["bun install", "bun run start", "bun run check:zero-orm", "bun run typecheck", "bun test", "bun run build"],
    "mw-rocksoul-gateway": ["go run ./cmd/mw-rocksoul-gateway", "go vet ./...", "go test -count=1 ./...", "CGO_ENABLED=0 go build ./..."],
    "mw-rocksoul-mcp": ["bun install", "bun run start", "bun run start:stdio", "bun run check:zero-orm", "bun run typecheck", "bun test"],
    "mw-rocksoul-sandbox": ["bun install", "bun run start", "bun run typecheck", "bun test"],
    "mw-stack": ["curl -fsSL https://raw.githubusercontent.com/A-L-L-A-H/mw-stack/main/install.sh | bash", "docker compose config -q", "bash -n install.sh", "bash -n mwctl"],
    "mw-studio": ["PYTHONPATH=src python -m mw_studio.server", "PYTHONPATH=src python -m mw_studio.worker", "PYTHONPATH=src python -m unittest discover -s tests -v"],
    "mw-templates": ["node scripts/verify-catalog.mjs", "node --test scripts/validate-compose-security.test.mjs", "node scripts/validate-compose-security.mjs"],
    "mw-ww": ["go run ./cmd/mw-ww-cli -audit", "go test ./...", "go build -tags \"production\" -ldflags \"-H windowsgui\" -o mw-ww.exe ./cmd/mw-ww"],
    "mw-xv": ["bun install", "bun run build", "bun run dev", "bun test", "bun run typecheck", "bun run verify"],
}

def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def check_repo(name: str, entry: dict, findings: list[dict]) -> None:
    repo = WS_ROOT / name
    if not (repo / ".git").exists():
        findings.append({"repo": name, "kind": "missing", "detail": "not cloned"})
        return

    expected_branch = entry.get("defaultBranch")
    expected_remote = f"https://github.com/{entry['github']}.git"

    try:
        branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        # Skip branch check for feature branches (not matching defaultBranch)
        if branch != expected_branch and not branch.startswith(("readme-", "feat/", "fix/", "chore/", "docs/", "refactor/", "repo-hygiene-")):
            findings.append({"repo": name, "kind": "branch", "detail": f"{branch} != manifest {expected_branch}"})
    except subprocess.CalledProcessError:
        findings.append({"repo": name, "kind": "git", "detail": "rev-parse failed"})
        return

    try:
        remote = git(repo, "remote", "get-url", "origin")
        if remote.rstrip("/") != expected_remote.rstrip("/"):
            findings.append({"repo": name, "kind": "remote", "detail": f"{remote} != manifest {expected_remote}"})
    except subprocess.CalledProcessError:
        findings.append({"repo": name, "kind": "remote", "detail": "no origin"})

    readme = repo / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8", errors="replace")
        for section in README_SECTIONS:
            if f"## {section}" not in text:
                findings.append({"repo": name, "kind": "readme-section", "detail": f"missing '## {section}'"})

        # Validate commands in README against manifest
        if name in MANIFEST_COMMANDS:
            for cmd in MANIFEST_COMMANDS[name]:
                # Check if the key part of the command appears in README
                # Extract the first meaningful token
                key = cmd.split()[0] if cmd else ""
                if key and key not in text:
                    findings.append({"repo": name, "kind": "readme-command", "detail": f"README missing manifest command: {cmd}"})
    else:
        findings.append({"repo": name, "kind": "readme", "detail": "README.md absent"})

    port = entry.get("port")
    if port is not None and name in PORT_SOURCES:
        targets = PORT_SOURCES[name]
        found = False
        for target in targets:
            path = repo / target
            if path.is_file():
                haystacks = [path.read_text(encoding="utf-8", errors="replace")]
            elif path.is_dir():
                haystacks = [
                    p.read_text(encoding="utf-8", errors="replace")
                    for p in sorted(path.rglob("*"))
                    if p.is_file()
                    and p.suffix in {".go", ".rs", ".ts", ".py", ".md", ".toml", ".json"}
                    and "node_modules" not in p.parts
                    and "target" not in p.parts
                    and "dist" not in p.parts
                ]
            else:
                continue
            if any(re.search(rf"\b{port}\b", hay) for hay in haystacks):
                found = True
                break
        if not found:
            findings.append({"repo": name, "kind": "port", "detail": f"manifest port {port} not found in {targets}"})

    check_folder_contract(name, repo, findings)
    check_hygiene(name, repo, findings)


def check_folder_contract(name: str, repo: Path, findings: list[dict]) -> None:
    """Enforce Rule 6: no docs/, doc/, or documentation/ dirs in any repo except mw-docs."""
    if name == "mw-docs":
        return

    for root, dirnames, _ in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for d in dirnames:
            if d in FORBIDDEN_DOCS_DIRS:
                rel = (Path(root) / d).relative_to(repo)
                findings.append({
                    "repo": name,
                    "kind": "folder-docs",
                    "detail": f"repo-level {rel}/ not allowed (Rule 6); move to mw-docs",
                })


def check_hygiene(name: str, repo: Path, findings: list[dict]) -> None:
    """Check required hygiene files, lockfile policy, and AGENTS.md Rules 2, 5, 7, 8, 12."""
    for f in ["LICENSE", "CONTRIBUTING.md", "SECURITY.md", ".env.example", ".gitignore"]:
        if not (repo / f).exists():
            findings.append({"repo": name, "kind": "missing-hygiene", "detail": f"missing {f}"})

    # Rule 2: no .plan/ directory inside any repo
    if (repo / ".plan").exists():
        findings.append({"repo": name, "kind": "forbidden-plan", "detail": ".plan/ is forbidden inside repo (Rule 2); use /repo/.plan/"})

    # Rule 5: no agent config files/dirs inside any repo
    for entry_name in FORBIDDEN_AGENT_CONFIGS:
        if (repo / entry_name).exists():
            findings.append({"repo": name, "kind": "forbidden-agent-config", "detail": f"{entry_name} is forbidden inside repo (Rule 5)"})

    # Rule 7: no git-tracked binaries (*.exe, *.dll, *.so, *.dylib)
    try:
        all_tracked = git(repo, "ls-files").splitlines()
        for f in all_tracked:
            if Path(f).suffix.lower() in FORBIDDEN_BINARY_EXTS:
                findings.append({"repo": name, "kind": "tracked-binary", "detail": f"{f} is a tracked binary (Rule 7)"})
    except subprocess.CalledProcessError:
        pass

    # Rule 8: no stale attached worktrees (count <= 1)
    try:
        wt_lines = [line for line in git(repo, "worktree", "list", "--porcelain").splitlines() if line.startswith("worktree ")]
        if len(wt_lines) > 1:
            findings.append({"repo": name, "kind": "stale-worktree", "detail": f"{len(wt_lines)} attached worktrees (Rule 8 requires <= 1)"})
    except subprocess.CalledProcessError:
        pass

    # Rule 12: CI workflows present, <= 3 workflow files, gitleaks in ci.yml/deploy.yml, no broken commitlint config ref
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.exists():
        findings.append({"repo": name, "kind": "missing-ci", "detail": "missing .github/workflows"})
    else:
        wf_files = sorted(p for p in wf_dir.iterdir() if p.is_file() and p.suffix in {".yml", ".yaml"})
        if len(wf_files) > 3:
            findings.append({"repo": name, "kind": "ci-workflow-count", "detail": f"{len(wf_files)} workflows in .github/workflows (Rule 12 max 3)"})

        primary_wf = wf_dir / ("deploy.yml" if name == "mw-docs" else "ci.yml")
        if name == "mw-docs" and not primary_wf.exists() and (wf_dir / "ci.yml").exists():
            primary_wf = wf_dir / "ci.yml"
        if not primary_wf.exists():
            findings.append({"repo": name, "kind": "missing-ci", "detail": f"missing .github/workflows/{primary_wf.name}"})
        else:
            primary_text = primary_wf.read_text(encoding="utf-8", errors="replace")
            if "gitleaks" not in primary_text:
                findings.append({"repo": name, "kind": "ci-security", "detail": f".github/workflows/{primary_wf.name} missing gitleaks (Rule 12)"})

        for wf in wf_files:
            wf_text = wf.read_text(encoding="utf-8", errors="replace")
            if ".github/workflow-templates/commitlint.config.js" in wf_text:
                findings.append({"repo": name, "kind": "ci-commitlint", "detail": f".github/workflows/{wf.name} references missing .github/workflow-templates/commitlint.config.js"})

    # Lockfile policy by detected stack
    if (repo / "Cargo.toml").exists() and not (repo / "Cargo.lock").exists():
        findings.append({"repo": name, "kind": "missing-lockfile", "detail": "missing Cargo.lock"})
    # npm/bun lockfile only required when the repo has a package.json AND no Rust/Go manifest
    is_go_or_rust = (repo / "go.mod").exists() or (repo / "Cargo.toml").exists()
    if (repo / "package.json").exists() and not is_go_or_rust:
        has_bun = (repo / "bun.lock").exists()
        has_npm = (repo / "package-lock.json").exists()
        if not has_bun and not has_npm:
            findings.append({"repo": name, "kind": "missing-lockfile", "detail": "missing bun.lock or package-lock.json"})

    # Forbidden tracked env files (only flag if actually tracked in git)
    try:
        tracked = git(repo, "ls-files", ".env", ".env.production", ".env.local").splitlines()
        for f in tracked:
            findings.append({"repo": name, "kind": "tracked-env", "detail": f"{f} is committed; must not be committed"})
    except subprocess.CalledProcessError:
        pass


def check_duplicate_ports(manifest: dict, findings: list[dict]) -> None:
    port_map = {}
    for entry in manifest["repositories"]:
        port = entry.get("port")
        if port is not None:
            port_map.setdefault(port, []).append(entry["name"])
    for port, names in port_map.items():
        if len(names) > 1:
            findings.append({"repo": "workspace", "kind": "duplicate-port", "detail": f"port {port} used by {', '.join(names)}"})


def check_ci_template_security(findings: list[dict]) -> None:
    """Ensure CI templates themselves carry the required security gates."""
    checks = {
        "ci-go.yml": ["gitleaks", "govulncheck"],
        "ci-rust.yml": ["gitleaks", "cargo audit"],
        "ci-bun.yml": ["gitleaks", "bun audit"],
        "ci-python.yml": ["gitleaks", "pip-audit", "bandit"],
        "ci-expo.yml": ["gitleaks", "npm audit"],
        "ci-data.yml": ["gitleaks"],
    }
    tpl_root = WS_ROOT / ".github" / "workflow-templates"
    for filename, required in checks.items():
        path = tpl_root / filename
        if not path.exists():
            findings.append({"repo": "workspace", "kind": "ci-security", "detail": f"missing CI template {filename}"})
            continue
        text = path.read_text(encoding="utf-8")
        for needle in required:
            if needle not in text:
                findings.append({"repo": "workspace", "kind": "ci-security", "detail": f"{filename} missing security gate: {needle}"})


def main() -> int:
    as_json = "--json" in sys.argv
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    findings: list[dict] = []

    # Check duplicate ports in manifest
    check_duplicate_ports(manifest, findings)

    # Ensure CI templates carry required security gates
    check_ci_template_security(findings)

    for entry in manifest["repositories"]:
        check_repo(entry["name"], entry, findings)

    if as_json:
        print(json.dumps(findings, indent=2))
    elif findings:
        print(f"DRIFT ({len(findings)}):")
        for f in findings:
            print(f"  [{f['kind']}] {f['repo']}: {f['detail']}")
    else:
        print("No drift: branches, remotes, ports, and README sections match the manifest.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())