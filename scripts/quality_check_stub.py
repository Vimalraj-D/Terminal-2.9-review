#!/usr/bin/env python3
"""Write a quality_check.md stub for one audit run.

Fills only what static_check.json and task.toml already know. Judgement
replaces the whole file; this is the skeleton so the criterion order cannot
drift. The stub includes evidence Results, a compact Results Overview, and
Blocking Quality Gates.

    python3 scripts/quality_check_stub.py <task-dir> <audit-run-dir>
"""
from __future__ import annotations

import json
import os
import re
import sys

CRITERIA = [
    "verifiable",
    "solvable",
    "difficult",
    "interesting",
    "outcome_verified",
    "anti_cheat_robustness",
    "task_security",
    "functional_verification",
    "deterministic_reproducible",
    "essential_difficulty",
    "test_instruction_alignment",
    "novel",
    "agentic",
    "reviewable",
    "instruction_concision",
    "solution_quality",
    "separate_verifier_configured",
    "environment_hygiene",
    "structured_data_schema",
    "typos",
    "difficulty_explanation_quality",
    "solution_explanation_quality",
    "verification_explanation_quality",
    "category_and_tags",
    "no_extraneous_files",
    "verifier_execution_isolation",
    "ctrf_reporting",
    "do_not_modify_enforced",
    "binary_reward",
]

GATES = [
    "verifiable",
    "solvable",
    "difficulty_floor",
    "outcome_verified",
    "anti_cheat_robustness",
    "task_security",
    "functional_verification",
    "deterministic_reproducible",
    "test_instruction_alignment",
    "agentic",
    "separate_verifier_configured",
    "environment_hygiene",
    "structured_data_schema",
    "typos",
    "category_and_tags",
    "no_extraneous_files",
    "verifier_execution_isolation",
    "ctrf_reporting",
    "do_not_modify_enforced",
    "binary_reward",
]

N_A_OK = {
    "separate_verifier_configured",
    "difficulty_explanation_quality",
    "solution_explanation_quality",
    "verification_explanation_quality",
    "do_not_modify_enforced",
}

# Compact overview / blocking-gate marks. Detailed results use the lowercase
# form with a colon and evidence; these lines are mark + id only.
RESULT_TO_COMPACT = {
    "✅ pass": "✅ PASS",
    "❌ fail": "❌ FAIL",
    "➖ not_applicable": "➖ N/A",
    "➖ pending": "➖ pending",
}


def toml_val(text: str, key: str) -> str:
    m = re.search(rf"^\s*{re.escape(key)}\s*=\s*(.+)$", text, re.M)
    if not m:
        return ""
    raw = m.group(1).strip().strip('"')
    return raw


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: quality_check_stub.py <task-dir> <audit-run-dir>", file=sys.stderr)
        return 2
    task, run = sys.argv[1].rstrip("/"), sys.argv[2].rstrip("/")
    task_id = os.path.basename(task)
    toml = ""
    try:
        toml = open(os.path.join(task, "task.toml"), errors="ignore").read()
    except OSError:
        pass
    category = toml_val(toml, "category") or "?"
    claimed = toml_val(toml, "difficulty") or "?"

    static = {}
    sj = os.path.join(run, "static_check.json")
    if os.path.isfile(sj):
        try:
            static = json.load(open(sj))
        except json.JSONDecodeError:
            static = {}

    n_tests = static.get("test_count", "?")
    n_words = static.get("instruction_words", "?")
    counts = static.get("counts") or {}
    findings = static.get("findings") or []
    caps = static.get("capability_classes") or {}
    named_caps = [k for k in caps if not str(k).startswith("_")]
    execdep = caps.get("_execution_dependent", "?")
    floor_hit = any(f.get("tag") == "DIFFICULTY-FLOOR" for f in findings)

    static_lines = []
    for f in findings:
        loc = f.get("file") or ""
        if f.get("line"):
            loc = f"{loc}:{f['line']}"
        ev = (f.get("evidence") or f.get("what") or "").strip()
        static_lines.append(
            f"- **{f.get('tag', '?')}** ({f.get('severity', '?')}) — {loc} — {ev}".rstrip(" —")
        )
    if named_caps or execdep != "?":
        static_lines.append(
            f"- capability_classes: {', '.join(named_caps) or 'none'} "
            f"(execution-dependent tests: {execdep})"
        )
    if not static_lines:
        static_lines = ["- (none from static_check.py)"]

    results = []
    for cid in CRITERIA:
        hint = ""
        if cid == "verifiable":
            hint = f"static: {n_tests} tests; fill after R1/R3"
        elif cid == "difficult":
            hint = (
                "DIFFICULTY-FLOOR BLOCKER — fail this criterion unless discarded with a quote"
                if floor_hit
                else f"classes={','.join(named_caps) or 'none'} execdep={execdep}; "
                "fail only for floor / P1 / P3 R5=1 / P5 / broken caveat — not too_easy"
            )
        elif cid == "instruction_concision":
            hint = f"static: {n_words}w instruction"
        elif cid == "category_and_tags":
            hint = (
                f"claimed difficulty={claimed}; category={category}; "
                "do not fail on claimed vs assessed ladder"
            )
        elif cid in N_A_OK:
            hint = "N/A only if the bundle has no such field; otherwise fill"
        else:
            hint = "fill after probes + CHECKS.md judgement"
        results.append(f"➖ pending - {cid}: {hint}")

    overview = [f"➖ pending - {cid}" for cid in CRITERIA]
    gates = [f"➖ pending - {g}" for g in GATES]

    body = f"""========================================
# Quality Check — `{task_id}`

Submitted by **extracted** · category `{category}` · difficulty claimed `{claimed}` · assessed `<too_easy|easy|medium|hard>`

**Outcome: pending** — replace this stub. Quality score **?** (`needs_fixes|clean`). Complexity **`?`**. Fairness: ?

## Quality Check Results
{chr(10).join(results)}

## Quality Check Results Overview
{chr(10).join(overview)}

## Blocking Quality Gates
{chr(10).join(gates)}

Also blocking for this programme: (name broken caveat / R1 / hints only if they fail — not too_easy; DIFFICULTY-FLOOR is the difficulty_floor gate)

## Static compliance findings

static_check.py: BLOCKER {counts.get('BLOCKER', '?')} / MAJOR {counts.get('MAJOR', '?')} / MINOR {counts.get('MINOR', '?')}

{chr(10).join(static_lines)}

---

# Repair brief (creation workflow)

Replace this stub. Creation reads only this file.

## Do not touch

- (files and mechanisms that already work)

## B1 —

**Done when:**

## Acceptance (authored image)

| Check | Required |
|---|---|
| R1 | Image builds; PWD ≠ `/` |
| R3 | Reward 0, 0 tests passing |
| R4 | solve.sh then tests → reward 1 |
| R5 | Source-only, skip the lever step → reward 0 |
| R6 | Planted decoy → reward 0 |
| R7 | Shortcut → reward 0 |
| R8 | Deterministic, idempotent |
| R9 | Fresh rebuild still reward 1 |

## Observed probes (do not copy into the task)

```
R1  pending
```
"""
    out = os.path.join(run, "quality_check.md")
    with open(out, "w") as fh:
        fh.write(body)
    print(f"quality_check_stub → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
