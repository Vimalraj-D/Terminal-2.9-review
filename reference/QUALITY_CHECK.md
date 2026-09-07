# Author-facing quality check

Judgement writes two files into the audit run:

| File | Audience |
|---|---|
| `verdict.json` | Machine record. Schema in `CHECKS.md` § Output |
| `quality_check.md` | Creation workflow. This file |

Creation never reads `verdict.json`. If a finding is not in `quality_check.md`, it is not a finding they will fix.

## File shape (mandatory, this order)

```
========================================
# Quality Check — `<task-id>`

Submitted by **extracted** · category `<task.toml category>` · difficulty claimed `<task.toml>` · assessed `<too_easy|easy|medium|hard>`

**Outcome: PASS|FAIL** — one sentence. Quality score **N**. Complexity **`level`**. Fairness: teaches|ambushes.

## Quality Check Results
<one evidence line per criterion, in the table below, never reordered, never omitted>

## Quality Check Results Overview
<one compact line per criterion, same ids and order as Results, ✅ PASS / ❌ FAIL / ➖ N/A>

## Blocking Quality Gates
<one line per blocking gate, same names as the table>

Also blocking for this programme …   # only if ship=false for reasons not in the Harbor gate list

## Static compliance findings
- **TAG** (BLOCKER|MAJOR|MINOR) — file:line — quoted evidence.

---

# Repair brief (creation workflow)
<concrete repairs; empty only when Outcome is PASS and ship is true>
```

Marks: `✅ pass`, `❌ fail`, `➖ not_applicable`. Never leave `pending`.

Each results line is:

```
✅ pass - <id>: <evidence with paths and line numbers; under ~500 characters>
```

Immediately after Results, emit the compact overview (same criterion order, no evidence):

```
✅ PASS - <id>
❌ FAIL - <id>
➖ N/A - <id>
```

Overview marks must match Results (`pass`→`PASS`, `fail`→`FAIL`, `not_applicable`→`N/A`). Do not regroup fails to the top. This list is every criterion in Results, not the Harbor gate subset.

`not_applicable` is allowed only for: `separate_verifier_configured`, `difficulty_explanation_quality`, `solution_explanation_quality`, `verification_explanation_quality`, `do_not_modify_enforced` — and only when the bundle has no such field or constraint. Do not N/A a fail.

## Criteria (fill from CHECKS.md + probes)

**Score each defect once.** A Go Dockerfile that does not build is `verifiable` (R1), not also `solvable`, `environment_hygiene`, and `category_and_tags`. Instruction how-to / fixture names are `instruction_concision` (`HINTS` / `PRESCRIPTIVE`), not `anti_cheat_robustness` if R5 and R7 stayed 0. Pytest on PATH is `environment_hygiene`. Static `DIFFICULTY-FLOOR` is the **`difficulty_floor`** blocking gate. P1 / P3 / P5 / a `broken` caveat class live on **`difficult`**. Assessed `too_easy` / `ambushes` are labels, not gate fails.

If R1 fails, you may still judge `solvable` / `anti_cheat_robustness` / `test_instruction_alignment` on a labeled workaround image. Do **not** fail those gates solely because the authored image never ran. Fail them only for their own pass condition. R9 stays blocked; say so in Observed probes.

| id | Pass when | Fail only when |
|---|---|---|
| `verifiable` | Suite exists, pytest (or equivalent) is pinned, `test.sh` can run it on the **authored** image | R1; uvx `-w`; 0 tests; runner never starts. This is the home for “image does not build”. |
| `solvable` | `solve.sh` derives the fix (not `echo` of fixtures) **and** R4 is reward 1 on an image that can run it | Hardcoded oracle; R4 reward 0 / tests still failing after solve.sh. **Not** R1 — that is `verifiable`. If R4 is 1 on a workaround image, **pass** and note the workaround. |
| `difficult` | P1–P5 hold with quoted evidence; caveat classes the suite grades are not `broken` | P1 lookup; P3 R5=1; P5 NOP-PASS; a graded caveat class is `broken`. Do **not** fail solely because assessed level is `too_easy`. Static `DIFFICULTY-FLOOR` is the **`difficulty_floor`** blocking gate, not this criterion. |
| `interesting` | A working engineer would recognise the job | Toy / generated scaffolding only |
| `outcome_verified` | Tests assert behaviour of the artifact the agent produces | `IMPL-TEST`; grading source text |
| `anti_cheat_robustness` | R5 stays 0; R7 stays 0; tests do not auto-rebuild; tests/oracle/rubric not in the agent tree | R5=1; R7>0; suite rebuilds the binary. Doc/instruction spoilers are `HINTS` (`instruction_concision`), **not** this gate, unless they make a shortcut score 1. |
| `task_security` | No secrets, no runtime net beyond package install, no privileged, no harness-dir wipe | `NET-AT-RUNTIME`; `SECRET`; `PRIVILEGED` |
| `functional_verification` | Tests run the program and compare structured output | Keyword scan of agent source |
| `deterministic_reproducible` | R8 identical reward 1; pins; no unseeded RNG in the suite | R8 fail; floating `latest`. A wrong-language Dockerfile is R1, not non-determinism. |
| `essential_difficulty` | Hard part is the planted defect, not schema/format plumbing | Instruction already names the constant the tests want |
| `test_instruction_alignment` | Stated requirements are tested; those tests **flip** (fail R3, pass R4) | Core requirement untested; inverted / scenery test (NOP-PASS on the real defect). Unstated extras (whitespace trim, ELF magic) are **MINOR** `UNSPECIFIED-GRADING` — **do not fail this gate** if a correct solution still passes them and the stated contract is graded. |
| `novel` | Not a re-skin visible in this batch | Same mechanism, different nouns |
| `agentic` | ≥5 chained commands, intermediate state, not one-shot | Lookup + instruction names the file |
| `reviewable` | A reviewer can recompute expected values from instruction + env without `solution/` | Hidden convention |
| `instruction_concision` | ≤3 paragraphs, ≤20 requirement bullets, no how-to, absolute paths | `VERBOSE-INSTRUCTION`; `HINTS`; `PRESCRIPTIVE` |
| `solution_quality` | Strict mode, derives answer, idempotent, no tests/ edits | `HARDCODED-SOLUTION`; `NO-STRICT-MODE` |
| `separate_verifier_configured` | Harbor split image if the programme uses it | TB 2.0 single Dockerfile → N/A, do not invent a split |
| `environment_hygiene` | No tests/solution COPY; apt cleaned; pytest not on agent PATH; no leftover bak | `TEST-DEPS-IN-IMAGE`; `STALE-FILES`; `RESERVED-DIR`. Wrong compiler / missing `go.mod` is `verifiable`, not hygiene. |
| `structured_data_schema` | If JSON/CSV/YAML is required, fields are stated | `SCHEMA-UNSPECIFIED` |
| `typos` | Names and instruction paths resolve | `A3.11` |
| `difficulty_explanation_quality` | Field present and specific | Missing in TB 2.0 `task.toml` → N/A |
| `solution_explanation_quality` | Field present and specific | Missing → N/A |
| `verification_explanation_quality` | Field present and specific | Missing → N/A |
| `category_and_tags` | Category fits; 3–6 specific tags | Missing category; tag count outside 3–6. Do **not** fail because claimed `task.toml` difficulty differs from assessed level — the ladder is advisory. Do not fail this gate for a leftover Dockerfile language — that is `verifiable`. |
| `no_extraneous_files` | Every shipped file is referenced or a planted decoy | Dead file with a “not used” comment |
| `verifier_execution_isolation` | `/tests` not in the agent image; reward from pytest rc | Suite COPY; reward from agent-writable file |
| `ctrf_reporting` | `test.sh` writes `--ctrf /logs/verifier/ctrf.json` | Missing flag |
| `do_not_modify_enforced` | Instruction names a read-only artifact and tests enforce it | No such constraint → N/A |
| `binary_reward` | `reward.txt` is literal 0/1 from pytest rc, both branches | `NO-REWARD-FILE` |

Discard static_check findings that are false positives (quote why). Never flag apt as `UNPINNED` — apt is exempt. Still flag `:latest` and unpinned language packages.

## Blocking Quality Gates

Emit one line per row, **this order**, `✅ PASS` / `❌ FAIL` / `➖ N/A`. Do not regroup fails to the top. This is the Harbor gate subset — not a copy of Results Overview (`difficulty_floor` lives only here; `interesting`, `novel`, `instruction_concision`, … live only in Results / Overview).

`verifiable`, `solvable`, `difficulty_floor`, `outcome_verified`, `anti_cheat_robustness`, `task_security`, `functional_verification`, `deterministic_reproducible`, `test_instruction_alignment`, `agentic`, `separate_verifier_configured`, `environment_hygiene`, `structured_data_schema`, `typos`, `category_and_tags`, `no_extraneous_files`, `verifier_execution_isolation`, `ctrf_reporting`, `do_not_modify_enforced`, `binary_reward`.

`difficulty_floor` is the static `DIFFICULTY-FLOOR` BLOCKER (≥2 capability classes, or 1 + ≥3 execution-dependent tests). Pass when that BLOCKER is absent (or discarded with a quoted reason). Fail when it is outstanding. It is not `too_easy` and not P1.

If `ship` is false for a `broken` caveat class, failed R1, or instruction hints, add one extra sentence after the gate list naming those. Do not hide them only in the results. Do **not** add a sentence solely because assessed level is `too_easy` or fairness is `ambushes`. `DIFFICULTY-FLOOR` belongs on **`difficulty_floor`**, not in “Also blocking”.

## Repair brief

Required whenever Outcome is FAIL. Creation must be able to act without asking a question.

1. **Do not touch** — files and mechanisms that already work (so they are not rewritten away).
2. **B1, B2, …** — blockers first, cheapest leverage first, each with file, current vs required, and **Done when** (a probe or a grep).
3. **Complexity redesign** only when a deterministic floor failed — `DIFFICULTY-FLOOR`, a quoted P1–P5 miss, or a `broken` caveat class. Name the missing class or property, quote the probe or test, and give the concrete plant. Do **not** demand a redesign solely because the advisory level is `too_easy`.
4. **Acceptance table** — R1–R9 plus instruction/metadata, on the **authored** image (no workaround).
5. **Observed probes** — KEY=VALUE lines. Quote, do not paste logs. Label workaround images.

Do not reduce the intended mechanism to dodge a requirement. Expanding scope is fine.

## Outcome vs `verdict.json`

| `quality_check.md` | `verdict.json` |
|---|---|
| Outcome FAIL | `ship: false` |
| Outcome PASS | `ship: true` |
| assessed `too_easy`/`easy`/`medium`/`hard` | `complexity.level` (advisory; does not drive Outcome) |
| Fairness teaches/ambushes | `complexity.fairness` (advisory; does not drive Outcome) |
| Quality score | `quality.score` |
| Static findings | `quality.findings` |
| Caveat legs (in results / repair) | `caveat_audit` |
| — | `verdict`: `ready_to_upload` iff `ship` is true |

They must not disagree. If they do, the markdown is wrong.
