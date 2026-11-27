#!/usr/bin/env python3
"""Zero-dependency polyglot code-quality and complexity gate for MoonWitness."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

SOURCE_EXTS: Dict[str, str] = {
    ".ts": "ts",
    ".tsx": "ts",
    ".js": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".go": "go",
    ".rs": "rs",
    ".py": "py",
}

URL_RE = re.compile(r"https?://\S+")
PURE_IMPORT_RE = re.compile(
    r"^\s*(?:import\b|export\s+.*\bfrom\b|from\s+\S+\s+import\b|use\s+\S+|package\s+\S+|#include\b)"
)
PURE_COMMENT_RE = re.compile(r"^\s*(?://|#|/\*|\*|\*/|///|//!)")

TS_FN_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(?:[A-Za-z_$][\w$]*)?\s*(?:<[^>\n]*>)?\s*\(([^)\n]*)\)"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*(?:async\s+)?(?:<[^>\n]*>)?\s*\(([^)\n]*)\)\s*(?::[^=\n]+)?=>"
    r"|^\s*(?:(?:public|private|protected|static|async|readonly)\s+)*([A-Za-z_$][\w$]*)\s*(?:<[^>\n]*>)?\s*\(([^)\n]*)\)\s*(?::[^{;\n]+)?\{"
)
TS_NON_FN_KEYWORDS = {"if", "for", "while", "switch", "catch", "constructor", "return", "else", "do", "try"}

GO_FN_RE = re.compile(
    r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_][\w]*)\s*(?:\[[^\]]*\])?\s*\(([^)]*)\)"
)
RS_FN_RE = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?(?:extern\s+\"[^\"]*\"\s+)?fn\s+([A-Za-z_][\w]*)\s*(?:<[^>]*>)?\s*\(([^)]*)\)"
)

COMPLEXITY_TOKEN_RE = re.compile(
    r"\b(?:if|elif|for|while|case|catch|match)\b|&&|\|\||\?(?!\.)|=>"
)

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SH_STRICT_RE = re.compile(r"^\s*set\s+-[a-zA-Z]*e[a-zA-Z]*\b")
SCRIPT_IGNORED_EXTS = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".gitkeep"}


@dataclass
class Violation:
    repo: str
    file: str
    line: int
    rule: str
    value: int
    limit: int
    detail: str


def workspace_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_policy(policy_path: Path) -> dict:
    with policy_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_repos(manifest_path: Path) -> List[str]:
    with manifest_path.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    return [entry["name"] for entry in manifest.get("repositories", []) if "name" in entry]


def is_excluded_dir(name: str, exclude_patterns: Sequence[str]) -> bool:
    if name.startswith(".worktree"):
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in exclude_patterns)


def is_test_file(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/")
    parts = [p.lower() for p in norm.split("/")]
    name = parts[-1]
    if any(p in {"__tests__", "tests", "test"} for p in parts[:-1]):
        return True
    return (
        ".test." in name
        or ".spec." in name
        or name.endswith("_test.go")
        or name.endswith("_test.py")
        or name.endswith("_test.rs")
        or name.startswith("test_")
    )


def split_params(raw: str, lang: str) -> int:
    text = raw.strip()
    if not text:
        return 0
    params: List[str] = []
    depth = 0
    buf: List[str] = []
    for ch in text:
        if ch in "([{<":
            depth += 1
            buf.append(ch)
        elif ch in ")]}>":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            part = "".join(buf).strip()
            if part:
                params.append(part)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        params.append(tail)
    if lang == "rs" and params and re.match(r"^(?:&\s*(?:mut\s+)?)?(?:mut\s+)?self\b", params[0]):
        params = params[1:]
    if lang == "py" and params and params[0].split(":")[0].split("=")[0].strip() in {"self", "cls"}:
        params = params[1:]
    return len(params)


def strip_strings_and_line_comments(line: str, lang: str) -> str:
    out: List[str] = []
    i = 0
    n = len(line)
    in_quote: Optional[str] = None
    while i < n:
        ch = line[i]
        if in_quote:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if lang != "py" and ch == "/" and i + 1 < n and line[i + 1] == "/":
            break
        if lang == "py" and ch == "#":
            break
        if ch in ("'", '"', "`"):
            in_quote = ch
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def check_markers(
    repo: str, rel_path: str, lines: Sequence[str], markers: Sequence[str]
) -> List[Violation]:
    if is_test_file(rel_path):
        return []
    violations: List[Violation] = []
    compiled = [
        (m, re.compile(r"\b" + re.escape(m) + r"\b") if m[0].isalpha() else re.compile(re.escape(m)))
        for m in markers
    ]
    for idx, line in enumerate(lines, start=1):
        for marker, pattern in compiled:
            if pattern.search(line):
                violations.append(
                    Violation(
                        repo=repo,
                        file=rel_path,
                        line=idx,
                        rule="forbidMarkers",
                        value=1,
                        limit=0,
                        detail=f"forbidden marker '{marker}'",
                    )
                )
    return violations


def check_line_lengths(
    repo: str, rel_path: str, lines: Sequence[str], max_len: int
) -> List[Violation]:
    violations: List[Violation] = []
    for idx, line in enumerate(lines, start=1):
        if len(line) <= max_len:
            continue
        if URL_RE.search(line) or PURE_IMPORT_RE.match(line) or PURE_COMMENT_RE.match(line):
            continue
        violations.append(
            Violation(
                repo=repo,
                file=rel_path,
                line=idx,
                rule="maxLineLength",
                value=len(line),
                limit=max_len,
                detail=f"line length {len(line)} > {max_len}",
            )
        )
    return violations


def match_brace_function(line: str, lang: str) -> Optional[Tuple[str, str]]:
    if lang in {"ts", "js"}:
        m = TS_FN_RE.match(line)
        if not m:
            return None
        if m.group(1) is not None:
            return ("function", m.group(1))
        if m.group(2) is not None:
            return (m.group(2), m.group(3) or "")
        name = m.group(4)
        if name and name not in TS_NON_FN_KEYWORDS:
            return (name, m.group(5) or "")
        return None
    if lang == "go":
        m = GO_FN_RE.match(line)
        return (m.group(1), m.group(2)) if m else None
    if lang == "rs":
        m = RS_FN_RE.match(line)
        return (m.group(1), m.group(2)) if m else None
    return None


def analyze_brace_functions(
    repo: str, rel_path: str, lines: Sequence[str], lang: str, policy: dict
) -> List[Violation]:
    violations: List[Violation] = []
    max_fn_lines = int(policy["maxFunctionLines"])
    max_cc = int(policy["maxCyclomaticComplexity"])
    max_depth = int(policy["maxNestingDepth"])
    max_params = int(policy["maxParams"])

    total = len(lines)
    idx = 0
    while idx < total:
        matched = match_brace_function(lines[idx], lang)
        if not matched:
            idx += 1
            continue
        fn_name, raw_params = matched
        param_count = split_params(raw_params, lang)
        start_line = idx + 1
        if param_count > max_params:
            violations.append(
                Violation(
                    repo=repo,
                    file=rel_path,
                    line=start_line,
                    rule="maxParams",
                    value=param_count,
                    limit=max_params,
                    detail=f"{fn_name} has {param_count} params > {max_params}",
                )
            )
        # Find opening brace of function body
        scan = idx
        brace_depth = 0
        opened = False
        max_nested = 0
        complexity = 1
        while scan < total:
            cleaned = strip_strings_and_line_comments(lines[scan], lang)
            opens = cleaned.count("{")
            closes = cleaned.count("}")
            if not opened and opens > 0:
                opened = True
            if opened:
                complexity += len(COMPLEXITY_TOKEN_RE.findall(cleaned))
                brace_depth += opens
                if brace_depth - 1 > max_nested:
                    max_nested = brace_depth - 1
                brace_depth -= closes
                if brace_depth <= 0:
                    break
            elif scan - idx > 5:
                break
            scan += 1
        if opened:
            fn_lines = scan - idx + 1
            if fn_lines > max_fn_lines:
                violations.append(
                    Violation(
                        repo=repo,
                        file=rel_path,
                        line=start_line,
                        rule="maxFunctionLines",
                        value=fn_lines,
                        limit=max_fn_lines,
                        detail=f"{fn_name} has {fn_lines} lines > {max_fn_lines}",
                    )
                )
            if complexity > max_cc:
                violations.append(
                    Violation(
                        repo=repo,
                        file=rel_path,
                        line=start_line,
                        rule="maxCyclomaticComplexity",
                        value=complexity,
                        limit=max_cc,
                        detail=f"{fn_name} complexity {complexity} > {max_cc}",
                    )
                )
            if max_nested > max_depth:
                violations.append(
                    Violation(
                        repo=repo,
                        file=rel_path,
                        line=start_line,
                        rule="maxNestingDepth",
                        value=max_nested,
                        limit=max_depth,
                        detail=f"{fn_name} nesting depth {max_nested} > {max_depth}",
                    )
                )
            idx = scan + 1
        else:
            idx += 1
    return violations


def _py_nesting_depth(node: ast.AST, current: int = 0) -> int:
    block_types = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)
    if hasattr(ast, "Match"):
        block_types = block_types + (ast.Match,)
    best = current
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        next_depth = current + 1 if isinstance(child, block_types) else current
        best = max(best, _py_nesting_depth(child, next_depth))
    return best


def _py_complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(0, len(child.values) - 1)
        elif hasattr(ast, "match_case") and isinstance(child, ast.match_case):
            score += 1
    return score


def analyze_python_functions(
    repo: str, rel_path: str, source: str, policy: dict
) -> List[Violation]:
    violations: List[Violation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    max_fn_lines = int(policy["maxFunctionLines"])
    max_cc = int(policy["maxCyclomaticComplexity"])
    max_depth = int(policy["maxNestingDepth"])
    max_params = int(policy["maxParams"])

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
        if args and args[0] in {"self", "cls"}:
            args = args[1:]
        param_count = len(args) + (1 if node.args.vararg else 0) + (1 if node.args.kwarg else 0)
        if param_count > max_params:
            violations.append(
                Violation(
                    repo=repo,
                    file=rel_path,
                    line=node.lineno,
                    rule="maxParams",
                    value=param_count,
                    limit=max_params,
                    detail=f"{node.name} has {param_count} params > {max_params}",
                )
            )
        end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
        fn_lines = end_line - node.lineno + 1
        if fn_lines > max_fn_lines:
            violations.append(
                Violation(
                    repo=repo,
                    file=rel_path,
                    line=node.lineno,
                    rule="maxFunctionLines",
                    value=fn_lines,
                    limit=max_fn_lines,
                    detail=f"{node.name} has {fn_lines} lines > {max_fn_lines}",
                )
            )
        cc = _py_complexity(node)
        if cc > max_cc:
            violations.append(
                Violation(
                    repo=repo,
                    file=rel_path,
                    line=node.lineno,
                    rule="maxCyclomaticComplexity",
                    value=cc,
                    limit=max_cc,
                    detail=f"{node.name} complexity {cc} > {max_cc}",
                )
            )
        depth = _py_nesting_depth(node, 0)
        if depth > max_depth:
            violations.append(
                Violation(
                    repo=repo,
                    file=rel_path,
                    line=node.lineno,
                    rule="maxNestingDepth",
                    value=depth,
                    limit=max_depth,
                    detail=f"{node.name} nesting depth {depth} > {max_depth}",
                )
            )
    return violations


def analyze_file(repo: str, file_path: Path, repo_root: Path, policy: dict) -> List[Violation]:
    ext = file_path.suffix.lower()
    lang = SOURCE_EXTS.get(ext)
    if not lang:
        return []
    rel_path = file_path.relative_to(repo_root).as_posix()
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = raw.splitlines()
    violations: List[Violation] = []

    line_limit = int(policy["maxTestFileLines"] if is_test_file(rel_path) else policy["maxFileLines"])
    if len(lines) > line_limit:
        violations.append(
            Violation(
                repo=repo,
                file=rel_path,
                line=len(lines),
                rule="maxFileLines",
                value=len(lines),
                limit=line_limit,
                detail=f"file has {len(lines)} lines > {line_limit}",
            )
        )

    violations.extend(check_line_lengths(repo, rel_path, lines, int(policy["maxLineLength"])))
    violations.extend(check_markers(repo, rel_path, lines, policy.get("forbidMarkers", [])))
    if lang == "py":
        violations.extend(analyze_python_functions(repo, rel_path, raw, policy))
    else:
        violations.extend(analyze_brace_functions(repo, rel_path, lines, lang, policy))
    return violations


def get_changed_files(repo_dir: Path) -> Set[Path]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return set()
    if proc.returncode != 0:
        return set()
    changed: Set[Path] = set()
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        rel = line[3:].strip()
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1].strip()
        rel = rel.strip('"')
        candidate = (repo_dir / rel).resolve()
        if candidate.is_file():
            changed.add(candidate)
    return changed


def check_scripts_standard(
    repo: str,
    repo_dir: Path,
    policy: dict,
    changed_set: Optional[Set[Path]] = None,
) -> List[Violation]:
    sp = policy.get("scriptsPolicy")
    if not isinstance(sp, dict):
        return []
    scripts_dir = repo_dir / "scripts"
    if not scripts_dir.is_dir():
        return []

    exclude = list(policy.get("excludeDirs", []))
    flat_threshold = int(sp.get("flatThreshold", 5))
    canonical_buckets = set(sp.get("canonicalBuckets", ["ci", "build", "release", "ops", "dev", "lib"]))
    forbidden_exts = {e.lower() for e in sp.get("forbiddenExtensions", [".cjs", ".bat", ".cmd"])}
    forbidden_prefixes = tuple(p.lower() for p in sp.get("forbiddenPrefixes", ["try", "tmp", "analyze", "compare", "fix_"]))
    max_cfg = sp.get("maxScripts", {})
    overrides = sp.get("repoOverrides", {})
    max_scripts = int(overrides.get(repo, max_cfg.get("default", 10)))

    script_files: List[Path] = []
    for root, dirs, filenames in os.walk(scripts_dir):
        dirs[:] = [d for d in dirs if not is_excluded_dir(d, exclude)]
        root_path = Path(root)
        for fname in filenames:
            fpath = root_path / fname
            if fpath.suffix.lower() in SCRIPT_IGNORED_EXTS or fname.startswith("."):
                continue
            script_files.append(fpath)

    violations: List[Violation] = []
    total_scripts = len(script_files)

    if changed_set is None and total_scripts > max_scripts:
        violations.append(
            Violation(
                repo=repo,
                file="scripts",
                line=1,
                rule="scriptsMaxCount",
                value=total_scripts,
                limit=max_scripts,
                detail=f"scripts/ has {total_scripts} scripts > {max_scripts}",
            )
        )

    for fpath in script_files:
        if changed_set is not None and fpath.resolve() not in changed_set:
            continue
        rel_repo = fpath.relative_to(repo_dir).as_posix()
        rel_scripts = fpath.relative_to(scripts_dir)
        ext = fpath.suffix.lower()
        stem = fpath.stem
        stem_lower = stem.lower()

        if ext in forbidden_exts:
            violations.append(
                Violation(
                    repo=repo,
                    file=rel_repo,
                    line=1,
                    rule="scriptsForbiddenExt",
                    value=1,
                    limit=0,
                    detail=f"forbidden script extension '{ext}'",
                )
            )

        for prefix in forbidden_prefixes:
            if stem_lower.startswith(prefix):
                violations.append(
                    Violation(
                        repo=repo,
                        file=rel_repo,
                        line=1,
                        rule="scriptsForbiddenPrefix",
                        value=1,
                        limit=0,
                        detail=f"forbidden scratch script prefix '{prefix}'",
                    )
                )
                break

        if not KEBAB_CASE_RE.match(stem):
            violations.append(
                Violation(
                    repo=repo,
                    file=rel_repo,
                    line=1,
                    rule="scriptsNaming",
                    value=1,
                    limit=0,
                    detail=f"script name '{stem}' must be kebab-case",
                )
            )

        if ext == ".sh":
            try:
                head_lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()[:15]
            except OSError:
                head_lines = []
            if not any(SH_STRICT_RE.match(ln) for ln in head_lines):
                violations.append(
                    Violation(
                        repo=repo,
                        file=rel_repo,
                        line=1,
                        rule="scriptsShellStrict",
                        value=1,
                        limit=0,
                        detail="shell script missing strict mode ('set -e' or 'set -euo pipefail')",
                    )
                )

        if total_scripts > flat_threshold:
            parts = rel_scripts.parts
            if len(parts) == 1:
                violations.append(
                    Violation(
                        repo=repo,
                        file=rel_repo,
                        line=1,
                        rule="scriptsFlatThreshold",
                        value=total_scripts,
                        limit=flat_threshold,
                        detail=f"flat script not allowed when scripts/ has {total_scripts} > {flat_threshold} scripts; move into canonical subdir",
                    )
                )
            elif parts[0] not in canonical_buckets:
                violations.append(
                    Violation(
                        repo=repo,
                        file=rel_repo,
                        line=1,
                        rule="scriptsCanonicalBucket",
                        value=1,
                        limit=0,
                        detail=f"subdir 'scripts/{parts[0]}' not in canonical buckets {sorted(canonical_buckets)}",
                    )
                )

    return violations


def scan_repo(
    repo: str, repo_dir: Path, policy: dict, changed_only: bool = False
) -> Tuple[int, List[Violation]]:
    if not repo_dir.is_dir():
        return (0, [])
    exclude = list(policy.get("excludeDirs", []))
    max_dir_files = int(policy["maxDirSourceFiles"])
    changed_set = get_changed_files(repo_dir) if changed_only else None

    files_scanned = 0
    violations: List[Violation] = []
    for root, dirs, filenames in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if not is_excluded_dir(d, exclude)]
        root_path = Path(root)
        source_files = [
            root_path / f for f in filenames if Path(f).suffix.lower() in SOURCE_EXTS
        ]
        if not changed_only and len(source_files) > max_dir_files:
            rel_dir = root_path.relative_to(repo_dir).as_posix()
            violations.append(
                Violation(
                    repo=repo,
                    file=rel_dir,
                    line=1,
                    rule="maxDirSourceFiles",
                    value=len(source_files),
                    limit=max_dir_files,
                    detail=f"directory has {len(source_files)} source files > {max_dir_files}",
                )
            )
        for src in source_files:
            if changed_set is not None and src.resolve() not in changed_set:
                continue
            files_scanned += 1
            violations.extend(analyze_file(repo, src, repo_dir, policy))
    violations.extend(check_scripts_standard(repo, repo_dir, policy, changed_set=changed_set))
    return (files_scanned, violations)


def build_summary(
    repo_stats: Dict[str, Tuple[int, List[Violation]]]
) -> Dict[str, object]:
    by_rule: Dict[str, int] = {}
    per_repo: Dict[str, Dict[str, int]] = {}
    total_files = 0
    total_violations = 0
    for repo, (files_count, violations) in sorted(repo_stats.items()):
        total_files += files_count
        total_violations += len(violations)
        per_repo[repo] = {"files": files_count, "violations": len(violations)}
        for v in violations:
            by_rule[v.rule] = by_rule.get(v.rule, 0) + 1
    return {
        "totalRepos": len(repo_stats),
        "totalFiles": total_files,
        "totalViolations": total_violations,
        "byRule": dict(sorted(by_rule.items())),
        "perRepo": per_repo,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MoonWitness polyglot quality gate")
    parser.add_argument("--repo", help="Scan only a single repository by name")
    parser.add_argument("--changed", action="store_true", help="Scan only git modified/untracked files")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any violation is found")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Emit JSON output")
    parser.add_argument("--summary", action="store_true", help="Emit compact summary output")
    parser.add_argument("--root", help="Override workspace root directory")
    parser.add_argument("--policy", help="Override quality-policy.json path")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else workspace_root()
    policy_path = Path(args.policy).resolve() if args.policy else (root / "quality-policy.json")
    manifest_path = root / "workspace.json"

    policy = load_policy(policy_path)
    repos = load_repos(manifest_path)
    if args.repo:
        repos = [r for r in repos if r == args.repo]
        if not repos:
            print(f"Unknown repository: {args.repo}", file=sys.stderr)
            return 2

    repo_stats: Dict[str, Tuple[int, List[Violation]]] = {}
    all_violations: List[Violation] = []
    for repo in repos:
        files_count, violations = scan_repo(repo, root / repo, policy, changed_only=args.changed)
        repo_stats[repo] = (files_count, violations)
        all_violations.extend(violations)

    summary = build_summary(repo_stats)
    if args.as_json:
        payload = {
            "summary": summary,
            "violations": [asdict(v) for v in all_violations],
        }
        print(json.dumps(payload, indent=2))
    elif args.summary:
        print(
            f"Quality summary: repos={summary['totalRepos']} "
            f"files={summary['totalFiles']} violations={summary['totalViolations']}"
        )
        for rule, count in summary["byRule"].items():
            print(f"  {rule}: {count}")
        for repo, stats in summary["perRepo"].items():
            print(f"  {repo}: files={stats['files']} violations={stats['violations']}")
    else:
        for v in all_violations:
            print(f"{v.repo}/{v.file}:{v.line} [{v.rule}] {v.detail}")
        print(
            f"Scanned {summary['totalFiles']} files across {summary['totalRepos']} repos: "
            f"{summary['totalViolations']} violations"
        )

    if args.strict and all_violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
