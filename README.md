# Terminal-Bench review repo

Drop a task zip in **Inbox**, extract it, then audit. Results accumulate under **audit**.

```
Inbox/        ← paste task .zip files here
extracted/    ← unzipped task trees (scratch only)
audit/        ← every audit run + verdict.json + quality_check.md
scripts/      ← static_check, probe, quality_check stub/lint, review workflow
reference/    ← CHECKS.md (rules) + QUALITY_CHECK.md (author-facing shape)
```

`Inbox/`, `extracted/`, and `audit/` are pushed as empty shells. Each has its own `.gitignore` (`*` + `!.gitignore`), so zips, extracted trees, and audit results never leave the machine.

## Quick start

```bash
# 1. Put the authored task archive in Inbox/
cp /path/to/my-task.zip Inbox/

# 2. Extract (+ optional full pipeline)
./scripts/review.sh extract              # all zips in Inbox
./scripts/review.sh audit my-task        # static check → audit/my-task/<timestamp>/
# or both:
./scripts/review.sh all

# Skip Docker probes during audit:
SKIP_PROBE=1 ./scripts/review.sh audit my-task
```

Each audit run folder gets `static_check.json`, `probe.txt`, a `verdict.json` stub, and a `quality_check.md` stub. Finish judgement by replacing both stubs. Score each defect on **one** quality-check criterion (`reference/QUALITY_CHECK.md`): R1 is `verifiable`, not `solvable`; R5=0/R7=0 is a pass on `anti_cheat_robustness`. Assessed `too_easy` and `ambushes` are advisory — they do not fail Outcome. `DIFFICULTY-FLOOR` and a `broken` caveat class do.

- `verdict.json` — `reference/CHECKS.md`
- `quality_check.md` — `reference/QUALITY_CHECK.md` (this is what you hand to creation). Must include a compact **Quality Check Results Overview** (`✅ PASS` / `❌ FAIL` / `➖ N/A`, every criterion) between the evidence Results list and Blocking Quality Gates.

```bash
./scripts/review.sh lint my-task    # fail if quality_check.md is still a stub
```

`audit/<task-id>/latest` always points at the newest run.
