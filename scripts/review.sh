#!/usr/bin/env bash
# Review-repo workflow: Inbox zip → extracted/ → audit/
#
#   ./scripts/review.sh extract [zip...]   # unpack Inbox zips into extracted/
#   ./scripts/review.sh audit <task-id>    # static check (+ optional probes) → audit/
#   ./scripts/review.sh lint <task-id>     # lint latest quality_check.md
#   ./scripts/review.sh all [zip...]       # extract then audit each
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INBOX="$ROOT/Inbox"
EXTRACTED="$ROOT/extracted"
AUDIT="$ROOT/audit"
STATIC="$ROOT/scripts/static_check.py"
PROBE="$ROOT/scripts/probe.sh"
QC_STUB="$ROOT/scripts/quality_check_stub.py"
QC_LINT="$ROOT/scripts/quality_check_lint.py"

usage() {
  cat <<'EOF'
Review-repo workflow: Inbox zip → extracted/ → audit/

  ./scripts/review.sh extract [zip...]   # unpack Inbox zips into extracted/
  ./scripts/review.sh audit <task-id>    # static check (+ optional probes) → audit/
  ./scripts/review.sh lint <task-id>     # lint audit/<id>/latest/quality_check.md
  ./scripts/review.sh all [zip...]       # extract then audit each

SKIP_PROBE=1 skips Docker probes during audit.
After audit, finish judgement into verdict.json AND quality_check.md
(see reference/QUALITY_CHECK.md). Creation reads quality_check.md only.
EOF
  exit 1
}

# Resolve task root inside an extracted tree (zip may wrap one top-level folder).
find_task_dir() {
  local base="$1"
  if [[ -f "$base/task.toml" ]]; then
    echo "$base"
    return
  fi
  local child
  child="$(find "$base" -mindepth 1 -maxdepth 2 -type f -name task.toml 2>/dev/null | head -1)"
  if [[ -n "$child" ]]; then
    dirname "$child"
    return
  fi
  return 1
}

stamp() { date +%Y%m%d-%H%M%S; }

extract_one() {
  local zip="$1"
  [[ -f "$zip" ]] || { echo "missing zip: $zip" >&2; return 1; }
  [[ "$zip" == *.zip ]] || { echo "not a zip: $zip" >&2; return 1; }

  local base name dest
  base="$(basename "$zip" .zip)"
  # sanitize folder name
  name="$(echo "$base" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/-/g')"
  dest="$EXTRACTED/$name"

  rm -rf "$dest"
  mkdir -p "$dest"
  unzip -q -o "$zip" -d "$dest"

  local task
  if ! task="$(find_task_dir "$dest")"; then
    echo "EXTRACT_FAIL task_id=$name reason=no_task.toml zip=$zip" >&2
    return 1
  fi

  # If zip dumped contents one level deeper, normalize to extracted/<name>/ as task root
  if [[ "$task" != "$dest" ]]; then
    local tmp="$EXTRACTED/.tmp-$name-$$"
    rm -rf "$tmp"
    mv "$task" "$tmp"
    rm -rf "$dest"
    mv "$tmp" "$dest"
    task="$dest"
  fi

  echo "EXTRACT_OK task_id=$name path=$task zip=$(basename "$zip")"
}

cmd_extract() {
  local zips=()
  if [[ $# -eq 0 ]]; then
    shopt -s nullglob
    zips=("$INBOX"/*.zip)
    shopt -u nullglob
    if [[ ${#zips[@]} -eq 0 ]]; then
      echo "Inbox is empty — drop a task .zip into $INBOX" >&2
      exit 1
    fi
  else
    for z in "$@"; do
      if [[ -f "$z" ]]; then
        zips+=("$z")
      elif [[ -f "$INBOX/$z" ]]; then
        zips+=("$INBOX/$z")
      elif [[ -f "$INBOX/$z.zip" ]]; then
        zips+=("$INBOX/$z.zip")
      else
        echo "zip not found: $z" >&2
        exit 1
      fi
    done
  fi

  local ok=0
  for z in "${zips[@]}"; do
    extract_one "$z" && ok=$((ok + 1)) || true
  done
  echo "extracted $ok / ${#zips[@]} zip(s) → $EXTRACTED"
}

cmd_audit() {
  local id="${1:?usage: review.sh audit <task-id>}"
  local task="$EXTRACTED/$id"
  [[ -d "$task" ]] || { echo "not extracted: $id (expected $task)" >&2; exit 1; }
  [[ -f "$task/task.toml" ]] || {
    local found
    found="$(find_task_dir "$task" || true)"
    [[ -n "${found:-}" ]] || { echo "no task.toml under $task" >&2; exit 1; }
    task="$found"
  }

  local run="$AUDIT/$id/$(stamp)"
  mkdir -p "$run"

  echo "--- static_check → $run/static_check.json"
  set +e
  python3 "$STATIC" "$task" --json >"$run/static_check.json"
  local sc=$?
  set -e
  python3 "$STATIC" "$task" >"$run/static_check.txt" || true
  echo "static_check_exit=$sc" | tee "$run/static_check.exit"

  if [[ "${SKIP_PROBE:-0}" != "1" ]] && command -v docker >/dev/null 2>&1; then
    echo "--- probe all → $run/probe.txt"
    set +e
    bash "$PROBE" "$task" all >"$run/probe.txt" 2>&1
    echo "probe_exit=$?" | tee "$run/probe.exit"
    set -e
  else
    echo "SKIP_PROBE=1 or no docker — wrote placeholder" | tee "$run/probe.txt"
  fi

  if [[ ! -f "$run/verdict.json" ]]; then
    printf '%s\n' '{' \
      '  "task_id": "'"$id"'",' \
      '  "status": "pending_judgement",' \
      '  "note": "Fill this file with the JSON schema from reference/CHECKS.md"' \
      '}' >"$run/verdict.json"
  fi

  echo "--- quality_check stub → $run/quality_check.md"
  python3 "$QC_STUB" "$task" "$run"

  # Stable "latest" pointer for this task
  ln -sfn "$(basename "$run")" "$AUDIT/$id/latest"

  echo "AUDIT_OK task_id=$id run=$run"
  echo "Next: complete judgement → $run/verdict.json and $run/quality_check.md"
  echo "      (creation reads quality_check.md; lint with: $0 lint $id)"
}

cmd_lint() {
  local id="${1:?usage: review.sh lint <task-id>}"
  local qc="$AUDIT/$id/latest/quality_check.md"
  [[ -f "$qc" ]] || { echo "no quality_check.md at $qc — run audit and finish judgement" >&2; exit 1; }
  python3 "$QC_LINT" "$qc"
}

cmd_all() {
  cmd_extract "$@"
  shopt -s nullglob
  local dirs=("$EXTRACTED"/*/)
  shopt -u nullglob
  for d in "${dirs[@]}"; do
    [[ -d "$d" ]] || continue
    local id
    id="$(basename "$d")"
    [[ "$id" == README.md || "$id" == .gitkeep ]] && continue
    [[ -f "$d/task.toml" || -n "$(find "$d" -maxdepth 2 -name task.toml 2>/dev/null | head -1)" ]] || continue
    cmd_audit "$id"
  done
}

case "${1:-}" in
  extract) shift; cmd_extract "$@" ;;
  audit)   shift; cmd_audit "$@" ;;
  lint)    shift; cmd_lint "$@" ;;
  all)     shift; cmd_all "$@" ;;
  *)       usage ;;
esac
