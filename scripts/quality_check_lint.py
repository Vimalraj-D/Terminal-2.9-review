#!/usr/bin/env python3
"""Lint an author-facing quality_check.md for required shape.

    python3 scripts/quality_check_lint.py <quality_check.md>
    python3 scripts/quality_check_lint.py audit/<task>/latest/quality_check.md

Exit 0 if the file can be handed to creation (all criteria present, overview
matches Results, no pending). Exit 1 if the shape is wrong or judgement was
not finished.
"""
from __future__ import annotations

import re
import sys

from quality_check_stub import CRITERIA, GATES, N_A_OK, RESULT_TO_COMPACT

MARK = re.compile(r"^(✅ pass|❌ fail|➖ not_applicable|➖ pending) - ([a-z_]+):")
# Compact overview and blocking-gate lines: mark + id, nothing else.
COMPACT = re.compile(r"^(✅ PASS|❌ FAIL|➖ N/A|➖ pending) - ([a-z_]+)\s*$")
GATE = COMPACT

OVERVIEW_HDR = "## Quality Check Results Overview"
GATES_HDR = "## Blocking Quality Gates"
RESULTS_HDR = "## Quality Check Results"


def _collect(section: str, regex: re.Pattern[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for line in section.splitlines():
        m = regex.match(line.strip())
        if m:
            found.append((m.group(1), m.group(2)))
    return found


def _ids_ok(found: list[tuple[str, str]], expected: list[str], label: str, errs: list[str]) -> None:
    ids = [i for _, i in found]
    if ids == expected:
        return
    errs.append(
        f"{label} must list every id in spec order; "
        f"got {len(ids)} ids, expected {len(expected)}"
    )
    missing = [c for c in expected if c not in ids]
    extra = [c for c in ids if c not in expected]
    if missing:
        errs.append("missing: " + ", ".join(missing))
    if extra:
        errs.append("unknown: " + ", ".join(extra))
    for i, (got, exp) in enumerate(zip(ids, expected)):
        if got != exp:
            errs.append(f"{label}[{i}] got {got!r} expected {exp!r}")
            break


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: quality_check_lint.py <quality_check.md>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    try:
        text = open(path, errors="ignore").read()
    except OSError as e:
        print(f"missing {path}: {e}", file=sys.stderr)
        return 1

    errs = []
    if "# Quality Check —" not in text:
        errs.append("missing '# Quality Check —'")
    if "## Quality Check Results" not in text:
        errs.append("missing '## Quality Check Results'")
    if OVERVIEW_HDR not in text:
        errs.append(f"missing {OVERVIEW_HDR!r}")
    if "## Blocking Quality Gates" not in text:
        errs.append("missing '## Blocking Quality Gates'")
    if "## Static compliance findings" not in text:
        errs.append("missing '## Static compliance findings'")
    if "# Repair brief" not in text:
        errs.append("missing '# Repair brief'")

    # Results evidence: after Results header, before Overview (fallback: Gates).
    after_results = text.split(RESULTS_HDR, 1)[-1]
    if OVERVIEW_HDR in after_results:
        results_sec, after_overview = after_results.split(OVERVIEW_HDR, 1)
        overview_sec = after_overview.split(GATES_HDR, 1)[0]
    else:
        results_sec = after_results.split(GATES_HDR, 1)[0]
        overview_sec = ""

    found = _collect(results_sec, MARK)
    _ids_ok(found, CRITERIA, "Quality Check Results", errs)
    for mark, cid in found:
        if mark == "➖ pending":
            errs.append(f"pending criterion: {cid}")
        if mark == "➖ not_applicable" and cid not in N_A_OK:
            errs.append(f"not_applicable not allowed for {cid}")

    ofound = _collect(overview_sec, COMPACT)
    _ids_ok(ofound, CRITERIA, "Quality Check Results Overview", errs)
    for mark, cid in ofound:
        if mark == "➖ pending":
            errs.append(f"pending overview: {cid}")

    rmap = {cid: mark for mark, cid in found}
    omap = {cid: mark for mark, cid in ofound}
    for cid in CRITERIA:
        if cid not in rmap or cid not in omap:
            continue
        want = RESULT_TO_COMPACT.get(rmap[cid])
        if want is None:
            continue
        if omap[cid] != want:
            errs.append(
                f"{cid}: Quality Check Results is {rmap[cid]!r} but "
                f"Overview is {omap[cid]!r} (expected {want!r})"
            )

    gates_sec = text.split(GATES_HDR, 1)[-1].split("## Static compliance findings", 1)[0]
    gfound = _collect(gates_sec, GATE)
    _ids_ok(gfound, GATES, "Blocking Quality Gates", errs)
    for mark, gid in gfound:
        if mark == "➖ pending":
            errs.append(f"pending gate: {gid}")

    gmap = {gid: mark for mark, gid in gfound}
    for gid in GATES:
        if gid not in rmap or gid not in gmap:
            continue
        rfail = "fail" in rmap[gid]
        gfail = "FAIL" in gmap[gid]
        rna = "not_applicable" in rmap[gid]
        gna = "N/A" in gmap[gid]
        if rfail != gfail or rna != gna:
            errs.append(
                f"{gid}: Quality Check Results is {rmap[gid]!r} but Blocking Quality Gates is {gmap[gid]!r}"
            )

    # One defect, one gate. These patterns were the over-fail mode.
    bodies = {}
    for line in results_sec.splitlines():
        m = MARK.match(line.strip())
        if m:
            bodies[m.group(2)] = line.lower()
    sol = bodies.get("solvable", "")
    if sol.startswith("❌ fail") and (
        "never builds" in sol or "authored image" in sol or "r1" in sol
    ):
        if "hardcoded" not in sol and "reward 0" not in sol:
            errs.append(
                "solvable fail cites R1/authored image — that belongs on verifiable; "
                "pass solvable if solve.sh derives and R4 is 1 on a runnable image"
            )
    ac = bodies.get("anti_cheat_robustness", "")
    if ac.startswith("❌ fail"):
        r5_held = re.search(r"r5.{0,100}(reward\s*0|stays reward 0|stay reward 0)", ac)
        r5_broke = re.search(r"r5.{0,100}(reward\s*1|scores 1)", ac)
        if r5_held and not r5_broke:
            errs.append(
                "anti_cheat_robustness fail while R5 stayed reward 0 — "
                "pass this gate; put instruction spoilers on instruction_concision"
            )
    ali = bodies.get("test_instruction_alignment", "")
    if ali.startswith("❌ fail") and (
        "all " in ali and "flip" in ali or "those are tested" in ali
    ):
        errs.append(
            "test_instruction_alignment fail while stating the contract is tested "
            "and flips — pass the gate; extras are MINOR UNSPECIFIED-GRADING"
        )
    cat = bodies.get("category_and_tags", "")
    if cat.startswith("❌ fail") and "too_easy" in cat:
        errs.append(
            "category_and_tags fail cites too_easy — the ladder is advisory; "
            "do not fail this gate on claimed vs assessed difficulty"
        )
    dif = bodies.get("difficult", "")
    if dif.startswith("❌ fail") and "too_easy" in dif:
        if not any(x in dif for x in ("difficulty-floor", "p1", "p3", "p5", "nop-pass", "r5", "broken", "caveat")):
            errs.append(
                "difficult fail cites too_easy without DIFFICULTY-FLOOR / P1 / P3 / P5 / "
                "broken caveat — the ladder label does not fail this criterion"
            )

    outcome = re.search(r"\*\*Outcome:\s*([^*]+)\*\*", text)
    if outcome and "pending" in outcome.group(1).lower():
        errs.append("Outcome is still pending")

    outcome_pass = bool(
        outcome and re.search(r"\bPASS\b", outcome.group(1), re.I)
        and "pending" not in outcome.group(1).lower()
    )
    static_sec = text.split("## Static compliance findings", 1)[-1]
    if "# Repair brief" in static_sec:
        static_sec = static_sec.split("# Repair brief", 1)[0]
    floor_blocker = bool(
        re.search(r"\*\*DIFFICULTY-FLOOR\*\*\s*\(\s*BLOCKER\s*\)", static_sec, re.I)
    )
    if outcome_pass and floor_blocker:
        errs.append(
            "Outcome is PASS while Static compliance findings still list "
            "DIFFICULTY-FLOOR (BLOCKER) — fail Outcome and difficulty_floor, or "
            "discard the finding with a quoted reason"
        )
    floor_gate = gmap.get("difficulty_floor", "")
    if "PASS" in floor_gate and floor_blocker:
        errs.append(
            "difficulty_floor is PASS while DIFFICULTY-FLOOR (BLOCKER) is listed — "
            "fail difficulty_floor or discard the static finding with a quoted reason"
        )

    if "➖ pending" in text:
        errs.append("file still contains '➖ pending'")

    if errs:
        print(f"FAIL {path}")
        for e in errs:
            print(f"  {e}")
        return 1
    print(f"OK {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
