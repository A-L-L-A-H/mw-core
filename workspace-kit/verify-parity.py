#!/usr/bin/env python3
"""Verify byte-for-byte parity between mw-core/workspace-kit and workspace root."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

KIT_FILES = [
    "AGENTS.md",
    "workspace.json",
    "quality-policy.json",
    "mw-ws.ps1",
    "mw-ws.sh",
    "scripts/drift.py",
    "scripts/quality.py",
    "scripts/quality_test.py",
]

WORKFLOW_TEMPLATE_DIR = ".github/workflow-templates"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_kit_files(kit_dir: Path) -> list[str]:
    files = list(KIT_FILES)
    tpl_dir = kit_dir / WORKFLOW_TEMPLATE_DIR
    if tpl_dir.is_dir():
        for entry in sorted(tpl_dir.iterdir()):
            if entry.is_file():
                files.append(f"{WORKFLOW_TEMPLATE_DIR}/{entry.name}")
    return files


def check_parity(kit_dir: Path, root_dir: Path) -> list[str]:
    mismatches: list[str] = []
    for rel in collect_kit_files(kit_dir):
        kit_path = kit_dir / rel
        root_path = root_dir / rel
        if not kit_path.is_file():
            mismatches.append(f"MISSING in kit: {rel}")
        elif not root_path.is_file():
            mismatches.append(f"MISSING in root: {rel}")
        elif sha256_file(kit_path) != sha256_file(root_path):
            mismatches.append(f"DRIFT: {rel}")
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Workspace root directory (default: two levels above workspace-kit)",
    )
    args = parser.parse_args()
    kit_dir = Path(__file__).resolve().parent
    mismatches = check_parity(kit_dir, args.root)
    if mismatches:
        for item in mismatches:
            print(item, file=sys.stderr)
        return 1
    print(f"OK: {len(collect_kit_files(kit_dir))} workspace-kit files match {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
