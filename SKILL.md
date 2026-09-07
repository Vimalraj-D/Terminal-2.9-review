---
name: tbench-task-check
description: >-
  Audit one authored Terminal-Bench task before it enters a corpus. Returns two
  verdicts — is it fair and valid (quality), and is enough difficulty actually
  planted (complexity: too_easy / easy / medium / hard) — plus a concrete repair
  for every finding. Runs the task's own code: builds the image, runs the suite
  against the unmodified tree and the reference solution, and probes for graded
  source text, dead decoys, shortcuts and non-determinism. Writes verdict.json
  and an author-facing quality_check.md (checklist + repair brief) for creation.
  Use when asked to check, audit, review, grade or difficulty-rate a Terminal-Bench
  or Harbor task bundle, or to tell an author how to make a task harder.
---

# Terminal-Bench task check

Two independent verdicts, never traded against each other. A task can be
beautifully built and far too easy; it can be brutally hard and unfair. Only a
task that passes both ships.

**Everything is fixable.** The author wrote the environment, the defect, the
tests, the rubric and the solution, so every finding ends in a repair they can
make. There is no rejecting verdict — `ship: false` means *not yet*.

## Review-repo folders

This skill lives in a review repo. Use the three staging folders — do not audit
out of a random path when the zip workflow is available:

| Folder | Role |
|---|---|
| `Inbox/` | Paste the authored task `.zip` here |
| `extracted/` | Unzip scratch only — working tree for the check |
| `audit/` | Every audit run, `verdict.json`, and `quality_check.md` |

```bash
./scripts/review.sh extract              # Inbox/*.zip → extracted/<task-id>/
./scripts/review.sh audit <task-id>      # static (+ probes) → stub quality_check.md
./scripts/review.sh lint <task-id>       # after judgement, fail if still pending
./scripts/review.sh all                  # extract then audit each
```

Then run the stages below against `extracted/<task-id>/`. Write **both**:

- `audit/<task-id>/<run>/verdict.json` — machine record (`reference/CHECKS.md` § Output)
- `audit/<task-id>/<run>/quality_check.md` — what creation reads (`reference/QUALITY_CHECK.md`)

`./scripts/review.sh audit` stubs `quality_check.md`. Judgement **replaces** that stub. Do not leave `➖ pending`. Lint with `./scripts/review.sh lint <task-id>`.

## Run it in this order

Each stage narrows what the next has to read. Do not skip ahead, and do not
re-derive by eye what an earlier stage already decided.

### 1 · Static checks — no model tokens

```bash
python3 scripts/static_check.py <task-dir>            # human-readable
python3 scripts/static_check.py <task-dir> --json     # machine-readable
python3 scripts/static_check.py <task-dir> --quiet    # findings only, no test skeleton
```

Settles every mechanical check: required files, `task.toml` fields, base-image
and language-package pinning (apt is exempt), harness-reserved directories,
reward-file branches, rubric arithmetic and format, absolute paths, test
docstrings, assertion quality (parsed with `ast`, resolving helper calls),
clone detection, oversize files, leftover `.bak`/`.orig`/`.git`, secrets,
vendor coupling, and the `DIFFICULTY-FLOOR` capability-class scan.

Exit code is the BLOCKER count. **A BLOCKER here usually means stop, report, and
let the author fix before anything else runs.** Keep
`capability_classes` from the JSON — judgement must not re-derive which classes
the suite grades.

Keep the `test_skeleton` it prints — names, line numbers, docstring flags and
assertion counts. That is what lets you read only the tests that matter.

### 2 · Runtime probes

```bash
scripts/probe.sh <task-dir> all       # R1 build, R3 unmodified, R4 reference, R8 determinism, R9 fresh build
scripts/probe.sh <task-dir> shell     # interactive, for R2 / R5 / R6 / R7
```

R2, R5, R6 and R7 need judgement — which step to skip, which decoy to take,
which shortcut to try — so drive those yourself in the shell. **R5 is the
sharpest probe there is**: apply only the solution's source edits, skip the
build or regeneration step the lever depends on, and confirm the reward stays 0.
If it reaches 1, grading reads the text the agent typed and the difficulty is
gone.

Quote the decisive line from a log. Never paste a log.

### 3 · Judgement

Load `reference/CHECKS.md` and `reference/QUALITY_CHECK.md`. CHECKS.md is the
rules. QUALITY_CHECK.md is the author-facing file shape: criterion order, marks
(`✅ pass` / `❌ fail` / `➖ not_applicable`), blocking gates, then a repair brief.

Only the judgement calls are left by this point — whether the defect survives
reading, whether the symptom sits a layer from its cause, whether the decoy is
plausible, the caveat audit for each graded capability class, where the task
lands on the (advisory) ladder, and what the author should add next.

**Ship does not use the ladder.** `too_easy` and `ambushes` are labels plus
`advice.steps`. `ship: false` only for a failed/blocked probe, an outstanding
BLOCKER (including `DIFFICULTY-FLOOR`), or a graded caveat class that is
`broken`. `verdict` on the JSON mirrors `ship`.

For every class in `capability_classes` (except `_execution_dependent`), fill
`caveat_audit`: instruction states the rule, environment makes the wrong move
tempting, solution shows the correct move — each with a quoted span. Copy the
same facts into `quality_check.md`. `broken` fails **`difficult`** and Outcome;
`weak` is a repair, not a fail. Static `DIFFICULTY-FLOOR` fails the
**`difficulty_floor`** blocking gate.

**Do not stack one defect across gates.** `QUALITY_CHECK.md` § Criteria is the
pass/fail contract:

- Authored image does not build (R1) → fail **`verifiable` only**. Pass
  **`solvable`** if `solve.sh` derives the answer and R4 is reward 1 on a
  labeled workaround image. Fail `solvable` only for a hardcoded oracle or R4
  still red after solve.sh.
- R5=0 and R7=0 → **pass `anti_cheat_robustness`**. Instruction/docs naming
  rebuild.sh or fixtures are `HINTS` / `PRESCRIPTIVE` on **`instruction_concision`**.
- Stated requirements tested and flipping → **pass `test_instruction_alignment`**.
  Unstated extras (trim, ELF magic) are MINOR, not a gate fail.
- Never flag apt as `UNPINNED`. Still flag `:latest` and unpinned language packages.
- Do **not** fail **`difficult`** or **`category_and_tags`** because the assessed
  level is `too_easy`. Fail **`difficulty_floor`** for `DIFFICULTY-FLOOR`. Fail
  `difficult` for P1 lookup, P3 R5=1, P5 NOP-PASS, or a `broken` caveat class.

## Reading budget

Accuracy first, but do not spend reading on what a command already decided.

- **Read in full** (small, and they carry most of the judgement): `instruction.md`, `solve.sh`, `test.sh`, `rubric.txt`, `task.toml`.
- **Never read `test_outputs.py` end to end.** Start from the skeleton; read the bodies of the tests tied to the central realisation and any test a probe flagged.
- **Do not walk the environment tree exhaustively.** Read what `solve.sh` touches, what those files import, and the decoys the rubric names. Sample the rest for voice and plausibility.
- **Evidence spans stay under ~200 characters.** A finding needs the decisive line, not the file.
- **Stop early on a structural blocker.** If the build fails or the reference solution does not pass, nothing downstream is trustworthy — report it with its repair and come back after the fix.

## Output

Write both files in the current audit run (`audit/<task-id>/latest/`):

1. **`verdict.json`** — schema in `reference/CHECKS.md` § Output.
2. **`quality_check.md`** — replace the stub. Shape in `reference/QUALITY_CHECK.md`.

Creation is given `quality_check.md` only. The repair brief at the bottom is the
work order (Do not touch → B1… → Done when → acceptance table). Checklist lines
must cite this task's paths, line numbers, and probe quotes — not generic
advice. After the evidence Results list, emit **Quality Check Results Overview**
— one `✅ PASS` / `❌ FAIL` / `➖ N/A` line per criterion, same order, matching
the Results marks — then the Blocking Quality Gates list.

Then:

```bash
./scripts/review.sh lint <task-id>
```

Two rules still govern the JSON and the markdown:

- **Never report a finding without a quoted span or quoted probe output.** A verdict without evidence is discarded and the check re-run.
- **`advice.steps` is never empty, at any level** — including `hard`. Authors are told what to add, not just what they scored, and the advice names this task's own files and artifacts. The same repairs must appear in the quality_check repair brief.

## Files

| Path | What it is |
|---|---|
| `Inbox/` | Drop task zip files to review |
| `extracted/` | Unpacked task trees (ephemeral) |
| `audit/` | Every audit run: `verdict.json`, `quality_check.md`, static/probe logs |
| `scripts/review.sh` | Extract → audit → lint orchestration |
| `scripts/static_check.py` | Every mechanical check, including `DIFFICULTY-FLOOR`, deterministic, no model tokens |
| `scripts/probe.sh` | Build and grading probes, with an interactive mode for the four that need judgement |
| `scripts/quality_check_stub.py` | Writes the quality_check.md skeleton after static_check |
| `scripts/quality_check_lint.py` | Confirms criterion order, Results Overview, no `pending`, repair brief present |
| `reference/CHECKS.md` | The full rules and the `verdict.json` schema. Load in stage 3 |
| `reference/QUALITY_CHECK.md` | Author-facing markdown shape. Load in stage 3 |
