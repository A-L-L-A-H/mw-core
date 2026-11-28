#!/usr/bin/env bash
set -euo pipefail

WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${WS_ROOT}/workspace.json"
CMD="${1:-status}"
FILTER="${2:-}"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "Missing workspace manifest: ${MANIFEST}" >&2
  exit 1
fi

parse_repos() {
  if command -v jq >/dev/null 2>&1; then
    jq -r '.repositories[] | [.name, .github, .defaultBranch, .stack, (.port // "-"), .profile, (.testCmd // "")] | @tsv' "${MANIFEST}"
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "${MANIFEST}" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    manifest = json.load(fh)
for r in manifest.get("repositories", []):
    port = "-" if r.get("port") is None else str(r.get("port"))
    print("\t".join([r["name"], r["github"], r["defaultBranch"], r["stack"], port, r["profile"], r.get("testCmd") or ""]))
PY
  else
    echo "Requires jq or python3 to parse workspace.json" >&2
    exit 1
  fi
}

matches_filter() {
  local name="$1" profile="$2" stack="$3"
  if [[ -z "${FILTER}" ]]; then
    return 0
  fi
  [[ "${name}" == *"${FILTER}"* || "${profile}" == "${FILTER}" || "${stack}" == *"${FILTER}"* ]]
}

case "${CMD}" in
  status)
    printf "%-14s %-22s %-10s %-6s %-10s %-6s\n" "REPO" "BRANCH" "HEAD" "DIRTY" "PROFILE" "PORT"
    printf "%-14s %-22s %-10s %-6s %-10s %-6s\n" "----" "------" "----" "-----" "-------" "----"
    while IFS=$'\t' read -r name github defbranch stack port profile testcmd; do
      matches_filter "${name}" "${profile}" "${stack}" || continue
      dir="${WS_ROOT}/${name}"
      if [[ ! -d "${dir}/.git" ]]; then
        printf "%-14s %-22s %-10s %-6s %-10s %-6s\n" "${name}" "MISSING" "-" "-" "${profile}" "${port}"
        continue
      fi
      branch="$(git -C "${dir}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo DETACHED)"
      head="$(git -C "${dir}" rev-parse --short HEAD 2>/dev/null || echo -)"
      dirty="$(git -C "${dir}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
      printf "%-14s %-22s %-10s %-6s %-10s %-6s\n" "${name}" "${branch}" "${head}" "${dirty}" "${profile}" "${port}"
    done < <(parse_repos)
    ;;

  pull)
    while IFS=$'\t' read -r name github defbranch stack port profile testcmd; do
      matches_filter "${name}" "${profile}" "${stack}" || continue
      dir="${WS_ROOT}/${name}"
      if [[ ! -d "${dir}/.git" ]]; then
        echo "[SKIP] ${name} not cloned (run './mw-ws.sh sync')"
        continue
      fi
      echo "[PULL] ${name}"
      git -C "${dir}" pull --ff-only || echo "[WARN] ${name} pull --ff-only failed"
    done < <(parse_repos)
    ;;

  sync)
    while IFS=$'\t' read -r name github defbranch stack port profile testcmd; do
      matches_filter "${name}" "${profile}" "${stack}" || continue
      dir="${WS_ROOT}/${name}"
      if [[ -d "${dir}/.git" ]]; then
        echo "[OK]   ${name} already present"
        continue
      fi
      echo "[CLONE] ${name} <- https://github.com/${github}.git"
      git clone "https://github.com/${github}.git" "${dir}"
    done < <(parse_repos)
    ;;

  test)
    failed=0
    while IFS=$'\t' read -r name github defbranch stack port profile testcmd; do
      matches_filter "${name}" "${profile}" "${stack}" || continue
      dir="${WS_ROOT}/${name}"
      if [[ ! -d "${dir}" || -z "${testcmd}" ]]; then
        echo "[SKIP] ${name}"
        continue
      fi
      echo "[TEST] ${name}: ${testcmd}"
      if [[ "${stack}" == "Rust" ]]; then
        (cd "${dir}" && CARGO_TARGET_DIR="${WS_ROOT}/cargo-target-${name}" bash -lc "${testcmd}") || failed=1
      else
        (cd "${dir}" && bash -lc "${testcmd}") || failed=1
      fi
    done < <(parse_repos)
    exit "${failed}"
    ;;

  ci)
    command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) is required" >&2; exit 1; }
    printf "%-14s %-16s %-12s %-12s\n" "REPO" "BRANCH" "STATUS" "CONCLUSION"
    while IFS=$'\t' read -r name github defbranch stack port profile testcmd; do
      matches_filter "${name}" "${profile}" "${stack}" || continue
      line="$(gh run list -R "${github}" -L 1 --json headBranch,status,conclusion -q '.[0] | [(.headBranch // "-"), (.status // "-"), (.conclusion // "-")] | @tsv' 2>/dev/null || true)"
      if [[ -z "${line}" ]]; then
        printf "%-14s %-16s %-12s %-12s\n" "${name}" "-" "NONE" "-"
      else
        IFS=$'\t' read -r b s c <<< "${line}"
        printf "%-14s %-16s %-12s %-12s\n" "${name}" "${b}" "${s}" "${c}"
      fi
    done < <(parse_repos)
    ;;

  health)
    printf "%-14s %-10s %-6s %-10s\n" "REPO" "PROFILE" "PORT" "STATE"
    while IFS=$'\t' read -r name github defbranch stack port profile testcmd; do
      matches_filter "${name}" "${profile}" "${stack}" || continue
      [[ "${port}" == "-" ]] && continue
      if curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
        state="UP"
      else
        state="DOWN"
      fi
      printf "%-14s %-10s %-6s %-10s\n" "${name}" "${profile}" "${port}" "${state}"
    done < <(parse_repos)
    ;;

  doctor)
    echo "=== Repositories ==="
    printf "%-14s %-14s %-22s %-6s\n" "REPO" "STATUS" "BRANCH" "DIRTY"
    printf "%-14s %-14s %-22s %-6s\n" "----" "------" "------" "-----"
    while IFS=$'\t' read -r name github defbranch stack port profile testcmd; do
      matches_filter "${name}" "${profile}" "${stack}" || continue
      dir="${WS_ROOT}/${name}"
      if [[ ! -d "${dir}" ]]; then
        printf "%-14s %-14s %-22s %-6s\n" "${name}" "[MISSING]" "-" "-"
        continue
      fi
      if [[ ! -d "${dir}/.git" ]]; then
        printf "%-14s %-14s %-22s %-6s\n" "${name}" "[NO-GIT]" "-" "-"
        continue
      fi
      branch="$(git -C "${dir}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo DETACHED)"
      dirty="$(git -C "${dir}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
      if [[ "${dirty}" == "0" ]]; then
        state="[CLEAN]"
      else
        state="[DIRTY (${dirty})]"
      fi
      printf "%-14s %-14s %-22s %-6s\n" "${name}" "${state}" "${branch}" "${dirty}"
    done < <(parse_repos)

    echo ""
    echo "=== Toolchains ==="
    printf "%-10s %-10s %s\n" "TOOL" "STATUS" "VERSION"
    printf "%-10s %-10s %s\n" "----" "------" "-------"
    for tool in go bun node cargo python git gh docker; do
      if command -v "${tool}" >/dev/null 2>&1; then
        if [[ "${tool}" == "go" ]]; then
          ver="$("${tool}" version 2>/dev/null | head -n 1 || echo unknown)"
        else
          ver="$("${tool}" --version 2>/dev/null | head -n 1 || echo unknown)"
        fi
        printf "%-10s %-10s %s\n" "${tool}" "[OK]" "${ver}"
      else
        printf "%-10s %-10s %s\n" "${tool}" "[MISSING]" "-"
      fi
    done

    echo ""
    echo "=== Disk Space ==="
    printf "%-8s %-10s %-10s %-10s\n" "DRIVE" "STATUS" "FREE_GB" "TOTAL_GB"
    printf "%-8s %-10s %-10s %-10s\n" "-----" "------" "-------" "--------"
    for drv in C Z; do
      lower_drv="$(echo "${drv}" | tr '[:upper:]' '[:lower:]')"
      mount_path="/${lower_drv}"
      if [[ -d "${mount_path}" ]]; then
        read -r total_gb free_gb < <(df -BG "${mount_path}" 2>/dev/null | awk 'NR==2 {gsub(/G/,"",$2); gsub(/G/,"",$4); print $2, $4}')
        printf "%-8s %-10s %-10s %-10s\n" "${drv}:" "[OK]" "${free_gb:-?}" "${total_gb:-?}"
      else
        printf "%-8s %-10s %-10s %-10s\n" "${drv}:" "[MISSING]" "-" "-"
      fi
    done
    ;;

  drift)
    python "${WS_ROOT}/scripts/drift.py"
    ;;

  lint)
    python3 "${WS_ROOT}/scripts/quality.py" "${@:2}"
    ;;

  *)
    echo "Usage: $0 {status|pull|sync|test|ci|health|doctor|drift|lint} [filter|args...]" >&2
    exit 2
    ;;
esac
