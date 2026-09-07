#!/usr/bin/env bash
# Runtime probes for one Terminal-Bench task bundle.
#
#   probe.sh <task-dir> [R1|R3|R4|R8|R9|all]
#
# Automates the probes that need no judgement. R2, R5, R6 and R7 need you to decide
# what to skip, what wrong fix to write and what shortcut to try, so run those with
# `probe.sh <task> shell` and drive the container yourself.
#
# Output is one KEY=VALUE line per probe plus a clipped tail on failure. It never
# prints a full log: read the tail, and only open the log file if the tail is not
# enough.
set -uo pipefail
TASK="${1:?usage: probe.sh <task-dir> [probe]}"
WHICH="${2:-all}"
TASK="${TASK%/}"
TASK="$(cd "$TASK" && pwd)"
NAME="$(basename "$TASK")"
IMG="tbcheck/$(echo "$NAME" | tr '[:upper:]' '[:lower:]')"
LOGS="${PROBE_LOGS:-/tmp/tbcheck/$NAME}"
mkdir -p "$LOGS"

tail_of() { tail -c 1200 "$1" 2>/dev/null | tr -d '\000' | sed 's/^/    | /'; }

build() {
  local tag="$1" t0 rc
  t0=$SECONDS
  docker build --network=none -t "$tag" "$TASK/environment" >"$LOGS/build.log" 2>&1
  rc=$?
  echo "build_sec=$((SECONDS-t0))"
  if [ $rc -ne 0 ]; then
    # offline build failed; retry with network so we can tell "needs net" from "broken"
    docker build -t "$tag" "$TASK/environment" >"$LOGS/build_net.log" 2>&1 && {
      echo "R1=fail reason=requires_network"; tail_of "$LOGS/build.log"; return 1; }
    echo "R1=fail reason=build_error"; tail_of "$LOGS/build.log"; return 1
  fi
  docker run --rm "$tag" sh -c 'test "$PWD" != "/"' >/dev/null 2>&1 \
    && echo "workdir_set=true" || echo "workdir_set=false"
  echo "R1=pass"
}

# run test.sh inside a fresh container, optionally after a setup command
grade() {                       # grade <label> [setup-cmd]
  local label="$1" setup="${2:-true}" rc rw vdir
  vdir="$LOGS/$label-verifier"
  rm -rf "$vdir"
  mkdir -p "$vdir"
  docker run --rm --network=none \
    -v "$TASK/tests:/tests:ro" -v "$TASK/solution:/solution:ro" \
    -v "$vdir:/logs/verifier" \
    "$IMG" bash -c "mkdir -p /logs/verifier; { $setup ; } && bash /tests/test.sh" \
    >"$LOGS/$label.log" 2>&1
  rc=$?
  rw=$(tr -d '[:space:]' <"$vdir/reward.txt" 2>/dev/null || true)
  if [[ "$rw" != "0" && "$rw" != "1" ]]; then
    rw="$([ $rc -eq 0 ] && echo 1 || echo 0)"
  fi
  echo "$rw"
}

probe_R3() {
  local rw; rw=$(grade R3 "true")
  local pass fail
  pass=$(grep -cE '^(PASSED|.*\bPASSED\b)' "$LOGS/R3.log" 2>/dev/null || echo 0)
  echo "R3_reward=$rw"
  [ "$rw" = "0" ] && echo "R3=pass" || { echo "R3=fail reason=nop_passes"; tail_of "$LOGS/R3.log"; }
  grep -oE '^[0-9]+ passed' "$LOGS/R3.log" | head -1 | sed 's/^/    already_passing: /'
}

probe_R4() {
  local t0=$SECONDS rw
  rw=$(grade R4 "bash /solution/solve.sh")
  echo "R4_reward=$rw verifier_sec=$((SECONDS-t0))"
  [ "$rw" = "1" ] && echo "R4=pass" || { echo "R4=fail reason=oracle_fail"; tail_of "$LOGS/R4.log"; }
}

probe_R8() {
  local a b c
  a=$(grade R8a "bash /solution/solve.sh")
  b=$(grade R8b "bash /solution/solve.sh")
  c=$(grade R8c "bash /solution/solve.sh && bash /solution/solve.sh")
  echo "R8_run1=$a R8_run2=$b R8_twice=$c"
  if [ "$a" = "$b" ] && [ "$a" = "$c" ] && [ "$a" = "1" ]; then echo "R8=pass idempotent=true"
  elif [ "$a" != "$b" ]; then echo "R8=fail reason=nondeterministic"; tail_of "$LOGS/R8b.log"
  else echo "R8=fail reason=not_idempotent"; tail_of "$LOGS/R8c.log"; fi
}

probe_R9() {
  docker rmi -f "$IMG" >/dev/null 2>&1
  build "$IMG" >/dev/null || { echo "R9=fail reason=rebuild_failed"; return; }
  local rw; rw=$(grade R9 "bash /solution/solve.sh")
  echo "R9_reward=$rw"
  [ "$rw" = "1" ] && echo "R9=pass" || { echo "R9=fail reason=dirty_state_dependency"; tail_of "$LOGS/R9.log"; }
}

case "$WHICH" in
  shell) docker run --rm -it --network=none \
           -v "$TASK/tests:/tests:ro" -v "$TASK/solution:/solution:ro" "$IMG" bash ;;
  R1)  build "$IMG" ;;
  all) build "$IMG" || exit 1
       echo "--- R3 unmodified";  probe_R3
       echo "--- R4 reference";   probe_R4
       echo "--- R8 determinism"; probe_R8
       echo "--- R9 fresh build"; probe_R9
       echo "--- R2/R5/R6/R7 need judgement: probe.sh $TASK shell" ;;
  *)   "probe_$WHICH" ;;
esac
echo "logs=$LOGS"
