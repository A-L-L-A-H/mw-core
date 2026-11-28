#!/usr/bin/env python3
"""Unit tests for z:/repo/scripts/quality.py."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quality  # noqa: E402


DEFAULT_POLICY = {
    "maxFileLines": 400,
    "maxTestFileLines": 800,
    "maxLineLength": 120,
    "maxFunctionLines": 60,
    "maxCyclomaticComplexity": 12,
    "maxNestingDepth": 4,
    "maxParams": 5,
    "maxDirSourceFiles": 30,
    "forbidMarkers": ["TODO", "FIXME", "HACK", "XXX", "@ts-ignore"],
    "excludeDirs": [".git", "node_modules", "vendor", "target", "dist", ".next*"],
    "scriptsPolicy": {
        "flatThreshold": 5,
        "canonicalBuckets": ["ci", "build", "release", "ops", "dev", "lib"],
        "allowedExtensions": [".mjs", ".sh", ".ps1", ".py"],
        "forbiddenExtensions": [".cjs", ".bat", ".cmd", ".exe", ".dll", ".so", ".dylib"],
        "forbiddenPrefixes": ["try", "tmp", "analyze", "compare", "fix_"],
        "maxScripts": {"default": 10, "ops": 25, "monorepo": 40},
        "repoOverrides": {"mw-stack": 25, "mw-xv": 40},
    },
}


class QualityAnalyzerTests(unittest.TestCase):
    def _analyze_temp_file(self, rel_path: str, content: str) -> list[quality.Violation]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return quality.analyze_file("test-repo", target, root, DEFAULT_POLICY)

    def test_typescript_pass_and_fail(self) -> None:
        clean_ts = """
import { somethingVeryLongFromAModule } from "https://example.com/a/very/long/url/that/exceeds/120/characters/easily/and/should/be/ignored";

export function greet(name: string, greeting: string): string {
  if (!name) {
    return greeting;
  }
  return `${greeting}, ${name}`;
}
"""
        self.assertEqual(self._analyze_temp_file("src/clean.ts", clean_ts), [])

        bad_ts = """
// TODO: fix this later
export function overloaded(a: number, b: number, c: number, d: number, e: number, f: number): number {
  if (a > 0) {
    if (b > 0) {
      if (c > 0) {
        if (d > 0) {
          if (e > 0) {
            return f;
          }
        }
      }
    }
  }
  return 0;
}
"""
        rules = {v.rule for v in self._analyze_temp_file("src/bad.ts", bad_ts)}
        self.assertIn("forbidMarkers", rules)
        self.assertIn("maxParams", rules)
        self.assertIn("maxNestingDepth", rules)

    def test_go_pass_and_fail(self) -> None:
        clean_go = """package sample

func Add(a int, b int) int {
\treturn a + b
}
"""
        self.assertEqual(self._analyze_temp_file("pkg/clean.go", clean_go), [])

        long_body = "\n".join("\tx++" for _ in range(65))
        bad_go = f"package sample\n\nfunc TooLong(a, b, c, d, e, f int) int {{\n\tx := 0\n{long_body}\n\treturn x\n}}\n"
        rules = {v.rule for v in self._analyze_temp_file("pkg/bad.go", bad_go)}
        self.assertIn("maxParams", rules)
        self.assertIn("maxFunctionLines", rules)

    def test_rust_pass_and_fail(self) -> None:
        clean_rs = """
pub fn compute(&self, a: i32, b: i32, c: i32, d: i32, e: i32) -> i32 {
    a + b + c + d + e
}
"""
        self.assertEqual(self._analyze_temp_file("src/lib.rs", clean_rs), [])

        branches = "\n".join(f"    if x == {i} {{ return {i}; }}" for i in range(13))
        bad_rs = f"pub fn complex(x: i32) -> i32 {{\n{branches}\n    0\n}}\n"
        rules = {v.rule for v in self._analyze_temp_file("src/complex.rs", bad_rs)}
        self.assertIn("maxCyclomaticComplexity", rules)

    def test_python_pass_and_fail(self) -> None:
        clean_py = """
class Worker:
    def run(self, a, b, c, d, e):
        if a:
            return b + c + d + e
        return 0
"""
        self.assertEqual(self._analyze_temp_file("app/clean.py", clean_py), [])

        bad_py = """
def deep_and_wide(a, b, c, d, e, f):
    if a:
        if b:
            if c:
                if d:
                    if e:
                        return f
    return 0
"""
        rules = {v.rule for v in self._analyze_temp_file("app/bad.py", bad_py)}
        self.assertIn("maxParams", rules)
        self.assertIn("maxNestingDepth", rules)

    def test_cli_modes_changed_json_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "demo-repo"
            repo_dir.mkdir()
            (root / "workspace.json").write_text(
                json.dumps({"repositories": [{"name": "demo-repo"}]}),
                encoding="utf-8",
            )
            (root / "quality-policy.json").write_text(
                json.dumps(DEFAULT_POLICY),
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "ci@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "CI"], check=True)

            committed = repo_dir / "committed.py"
            committed.write_text("# TODO: old debt\nx = 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo_dir), "add", "committed.py"], check=True)
            subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "init"], check=True, capture_output=True)

            untracked = repo_dir / "new_clean.py"
            untracked.write_text("def ok(a, b):\n    return a + b\n", encoding="utf-8")

            # --changed --strict should pass because committed.py is untouched
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = quality.main(["--root", str(root), "--changed", "--strict", "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["summary"]["totalFiles"], 1)
            self.assertEqual(data["summary"]["totalViolations"], 0)

            # Full scan with --summary should report 1 violation from committed.py
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = quality.main(["--root", str(root), "--summary"])
            self.assertEqual(rc2, 0)
            self.assertIn("violations=1", buf2.getvalue())

    def test_scripts_extensions_prefixes_naming_and_shell_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "mw-demo"
            scripts = repo_dir / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "check-health.mjs").write_text("export const ok = true;\n", encoding="utf-8")
            (scripts / "deploy-vps.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\necho ok\n", encoding="utf-8")
            self.assertEqual(quality.check_scripts_standard("mw-demo", repo_dir, DEFAULT_POLICY), [])

            (scripts / "legacy.cjs").write_text("module.exports = {};\n", encoding="utf-8")
            (scripts / "run.bat").write_text("@echo off\n", encoding="utf-8")
            (scripts / "win.cmd").write_text("@echo off\n", encoding="utf-8")
            (scripts / "try.mjs").write_text("console.log(1);\n", encoding="utf-8")
            (scripts / "analyze.mjs").write_text("console.log(2);\n", encoding="utf-8")
            (scripts / "fix_entries.cjs").write_text("module.exports = {};\n", encoding="utf-8")
            (scripts / "BadName.mjs").write_text("export const x = 1;\n", encoding="utf-8")
            (scripts / "unsafe-op.sh").write_text("#!/usr/bin/env bash\necho unsafe\n", encoding="utf-8")

            viols = quality.check_scripts_standard("mw-demo", repo_dir, DEFAULT_POLICY)
            by_file = {}
            for v in viols:
                by_file.setdefault(v.file, set()).add(v.rule)

            self.assertIn("scriptsForbiddenExt", by_file["scripts/legacy.cjs"])
            self.assertIn("scriptsForbiddenExt", by_file["scripts/run.bat"])
            self.assertIn("scriptsForbiddenExt", by_file["scripts/win.cmd"])
            self.assertIn("scriptsForbiddenPrefix", by_file["scripts/try.mjs"])
            self.assertIn("scriptsForbiddenPrefix", by_file["scripts/analyze.mjs"])
            self.assertIn("scriptsForbiddenPrefix", by_file["scripts/fix_entries.cjs"])
            self.assertIn("scriptsForbiddenExt", by_file["scripts/fix_entries.cjs"])
            self.assertIn("scriptsNaming", by_file["scripts/fix_entries.cjs"])
            self.assertIn("scriptsNaming", by_file["scripts/BadName.mjs"])
            self.assertIn("scriptsShellStrict", by_file["scripts/unsafe-op.sh"])

    def test_scripts_flat_threshold_and_canonical_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "mw-demo"
            scripts = repo_dir / "scripts"
            scripts.mkdir(parents=True)
            for i in range(5):
                (scripts / f"check-item-{i}.mjs").write_text("export {};\n", encoding="utf-8")
            self.assertEqual(quality.check_scripts_standard("mw-demo", repo_dir, DEFAULT_POLICY), [])

            # 6th flat script triggers scriptsFlatThreshold
            (scripts / "check-item-5.mjs").write_text("export {};\n", encoding="utf-8")
            viols = quality.check_scripts_standard("mw-demo", repo_dir, DEFAULT_POLICY)
            self.assertEqual(sum(1 for v in viols if v.rule == "scriptsFlatThreshold"), 6)

            # Moving into canonical buckets + one invalid bucket
            repo_dir2 = Path(tmp) / "mw-bucket"
            for bucket in ("ci", "build", "release", "ops", "dev", "lib"):
                d = repo_dir2 / "scripts" / bucket
                d.mkdir(parents=True)
                (d / f"run-{bucket}.mjs").write_text("export {};\n", encoding="utf-8")
            self.assertEqual(quality.check_scripts_standard("mw-bucket", repo_dir2, DEFAULT_POLICY), [])

            bad_dir = repo_dir2 / "scripts" / "misc"
            bad_dir.mkdir(parents=True)
            (bad_dir / "helper-one.mjs").write_text("export {};\n", encoding="utf-8")
            viols2 = quality.check_scripts_standard("mw-bucket", repo_dir2, DEFAULT_POLICY)
            self.assertEqual([v.rule for v in viols2], ["scriptsCanonicalBucket"])

    def test_scripts_max_count_ceilings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Standard repo ceiling = 10
            std_dir = Path(tmp) / "mw-std"
            (std_dir / "scripts" / "ci").mkdir(parents=True)
            for i in range(11):
                (std_dir / "scripts" / "ci" / f"check-{i}.mjs").write_text("export {};\n", encoding="utf-8")
            std_viols = quality.check_scripts_standard("mw-std", std_dir, DEFAULT_POLICY)
            self.assertEqual([v.rule for v in std_viols], ["scriptsMaxCount"])
            self.assertEqual(std_viols[0].limit, 10)

            # Ops repo (mw-stack) ceiling = 25
            ops_dir = Path(tmp) / "mw-stack"
            (ops_dir / "scripts" / "ops").mkdir(parents=True)
            for i in range(25):
                (ops_dir / "scripts" / "ops" / f"deploy-{i}.mjs").write_text("export {};\n", encoding="utf-8")
            self.assertEqual(quality.check_scripts_standard("mw-stack", ops_dir, DEFAULT_POLICY), [])
            (ops_dir / "scripts" / "ops" / "deploy-25.mjs").write_text("export {};\n", encoding="utf-8")
            ops_viols = quality.check_scripts_standard("mw-stack", ops_dir, DEFAULT_POLICY)
            self.assertEqual([v.rule for v in ops_viols], ["scriptsMaxCount"])
            self.assertEqual(ops_viols[0].limit, 25)

            # Monorepo (mw-xv) ceiling = 40
            mono_dir = Path(tmp) / "mw-xv"
            (mono_dir / "scripts" / "ci").mkdir(parents=True)
            for i in range(40):
                (mono_dir / "scripts" / "ci" / f"audit-{i}.mjs").write_text("export {};\n", encoding="utf-8")
            self.assertEqual(quality.check_scripts_standard("mw-xv", mono_dir, DEFAULT_POLICY), [])
            (mono_dir / "scripts" / "ci" / "audit-40.mjs").write_text("export {};\n", encoding="utf-8")
            mono_viols = quality.check_scripts_standard("mw-xv", mono_dir, DEFAULT_POLICY)
            self.assertEqual([v.rule for v in mono_viols], ["scriptsMaxCount"])
            self.assertEqual(mono_viols[0].limit, 40)

    def test_exclude_dirs_glob_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "mw-xv"
            (repo_dir / "apps" / "board" / "src").mkdir(parents=True)
            (repo_dir / "apps" / "board" / "src" / "clean.ts").write_text(
                "export function ok(a: number): number { return a + 1; }\n",
                encoding="utf-8",
            )
            for cache_dir in (".next", ".next-visual", ".next-e2e"):
                target = repo_dir / "apps" / "board" / cache_dir / "chunks"
                target.mkdir(parents=True)
                (target / "bundle.js").write_text(
                    "// TODO: generated cache\n" + ("x" * 200) + "\n",
                    encoding="utf-8",
                )

            files_scanned, violations = quality.scan_repo("mw-xv", repo_dir, DEFAULT_POLICY)
            self.assertEqual(files_scanned, 1)
            self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
