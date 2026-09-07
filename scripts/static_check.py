#!/usr/bin/env python3
"""Every mechanical check on a Terminal-Bench task bundle, decided without a model.

Run this FIRST. It settles the checks that are facts about files -- pins, paths,
rubric arithmetic, docstrings, reserved directories, leftover files -- so the model
spends its tokens on the judgement calls that scripts cannot make.

    python3 static_check.py <task-dir> [--json] [--quiet]

Exit code is the number of BLOCKERs, capped at 100. Output is compact by design:
one line per finding, evidence clipped, no file dumps.
"""
import sys, os, re, json, glob, argparse

VALID_SUB = {"long_context", "tool_specific", "api_integration", "db_interaction", "ui_building"}
LLM_VOICE = [r"\bLet's\b", r"In this task, you will", r"You are an? (expert|helpful)",
             r"\bcomprehensive\b", r"\brobust\b", r"\bseamless\b", r"\bdelve\b",
             r"It'?s worth noting", r"\bleverage\b"]
VAGUE = [r"\bmake it better\b", r"\bhandle errors properly\b", r"\boptimi[sz]e the code\b",
         r"\bas appropriate\b", r"\bif necessary\b", r"\bimprove the\b"]
NET = re.compile(r"(https?://(?!localhost|127\.0\.0\.1)[^\s\"')]+)")
NET_OK = re.compile(r"(pypi|files\.pythonhosted|registry\.npmjs|deb\.debian|archive\.ubuntu|"
                    r"security\.ubuntu|astral\.sh|golang\.org/dl|crates\.io|static\.crates\.io|"
                    r"apt\.|repo\.|dl-cdn\.alpinelinux|nodejs\.org/dist|sh\.rustup\.rs)", re.I)
SECRET = re.compile(r"(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|"
                    r"gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})")
# extra private terms come from VENDOR_TERMS (comma-separated env var) so no
# customer or programme name ever ships inside this file
_extra = [re.escape(t.strip()) for t in os.environ.get("VENDOR_TERMS", "").split(",") if t.strip()]
VENDOR = re.compile(r"\b(" + "|".join(_extra + [
    r"jira", r"linear\.app", r"asana", r"internal\.[a-z]+\.(?:com|net)",
    r"cohort[_-]?\d", r"batch[_-]?\d{2,}"]) + r")\b", re.I)
STALE = ("*.bak", "*.orig", "*.armbak", "*.swp", "*.swo", "*~", "*.rej", "*.tmp")


class Report:
    def __init__(self):
        self.f = []

    def add(self, sev, tag, what, file="", line=0, evidence=""):
        self.f.append({"severity": sev, "tag": tag, "what": what, "file": file,
                       "line": line, "evidence": evidence[:160].replace("\n", " ")})

    B = lambda s, *a, **k: s.add("BLOCKER", *a, **k)
    M = lambda s, *a, **k: s.add("MAJOR", *a, **k)
    N = lambda s, *a, **k: s.add("MINOR", *a, **k)


def read(p):
    try:
        return open(p, errors="ignore").read()
    except OSError:
        return ""


def lineno(text, needle):
    i = text.find(needle)
    return text[:i].count("\n") + 1 if i >= 0 else 0


# ---------------------------------------------------------------- structure
def check_structure(d, r):
    need = ["task.toml", "instruction.md", "environment/Dockerfile",
            "solution/solve.sh", "tests/test.sh", "tests/test_outputs.py"]
    for f in need:
        if not os.path.exists(os.path.join(d, f)):
            r.B("MISSING-FILE", f"required file absent: {f}", f)
    if not (os.path.exists(f"{d}/rubric.txt") or os.path.exists(f"{d}/rubrics.txt")):
        r.M("MISSING-RUBRIC", "no rubric.txt or rubrics.txt")
    for pat in STALE:
        for hit in glob.glob(f"{d}/**/{pat}", recursive=True):
            r.M("STALE-FILES", "leftover working file", os.path.relpath(hit, d))
    if os.path.isdir(f"{d}/.git") or glob.glob(f"{d}/**/.git", recursive=True):
        r.B("LEAK", "a .git directory ships with the task; history may hold the answer")
    for f in glob.glob(f"{d}/**/*", recursive=True):
        if os.path.isfile(f) and os.path.getsize(f) > 1_048_576:
            r.M("OVERSIZE", f"{os.path.getsize(f)//1024} KB, over the 1 MB limit",
                os.path.relpath(f, d))


# ----------------------------------------------------------------- manifest
def check_toml(d, r):
    t = read(f"{d}/task.toml")
    if not t:
        return {}
    def val(k):
        m = re.search(rf"^\s*{k}\s*=\s*(.+)$", t, re.M)
        return m.group(1).strip() if m else None
    got = {k: val(k) for k in ("category", "subcategories", "difficulty", "codebase_size",
                               "languages", "tags", "allow_internet", "build_timeout_sec",
                               "cpus", "memory_mb", "storage_mb", "author_name", "author_email")}
    for k in ("category", "subcategories", "difficulty", "codebase_size", "languages", "tags"):
        if got[k] is None:
            r.M("METADATA-DRIFT", f"[metadata] {k} missing", "task.toml")
    if t.count("timeout_sec") < 2:
        r.M("METADATA-DRIFT", "agent and verifier timeouts must both be declared", "task.toml")
    if got["subcategories"]:
        for sc in re.findall(r'"([^"]+)"', got["subcategories"]):
            if sc not in VALID_SUB:
                r.M("METADATA-DRIFT", f"unknown subcategory {sc!r}", "task.toml")
    if got["tags"]:
        n = len(re.findall(r'"[^"]+"', got["tags"]))
        if not 3 <= n <= 6:
            r.M("METADATA-DRIFT", f"{n} tags; the bar is 3-6", "task.toml")
    if got["languages"] and len(re.findall(r'"[^"]+"', got["languages"])) > 3:
        r.N("METADATA-DRIFT", "many languages listed; list only the main ones", "task.toml")
    if got["allow_internet"] and "true" in got["allow_internet"]:
        r.B("NET-AT-RUNTIME", "allow_internet = true", "task.toml",
            lineno(t, "allow_internet"))
    if VENDOR.search(t):
        r.M("VENDOR", "vendor or platform coupling in the manifest", "task.toml",
            evidence=VENDOR.search(t).group(0))
    return got


# --------------------------------------------------------------- dockerfile
def check_docker(d, r):
    p = "environment/Dockerfile"
    s = read(f"{d}/{p}")
    if not s:
        return
    froms = re.findall(r"^FROM\s+(\S+)", s, re.M)
    for f in froms:
        if "@sha256:" in f:
            continue
        if f.endswith(":latest") or ":" not in f.split("/")[-1]:
            r.M("UNPINNED", f"base image not pinned: {f}", p, lineno(s, f))
        else:
            r.N("UNPINNED", f"tag pin only, digest preferred: {f}", p, lineno(s, f))
    if "WORKDIR" not in s:
        r.B("NO-WORKDIR", "no WORKDIR; tests/test.sh aborts when PWD is /", p)
    for m in re.finditer(r"^\s*(?:RUN|COPY|ADD)[^\n]*?(/(?:tests|solution)\b)", s, re.M):
        r.B("RESERVED-DIR", f"Dockerfile touches harness-reserved {m.group(1)}", p,
            s[:m.start()].count("\n") + 1)
    for m in re.finditer(r"^\s*COPY\s+[^\n]*\b(tests?/|solution/|solve\.sh|test_outputs\.py|test\.sh)",
                         s, re.M):
        r.B("LEAK", "solution or tests copied into the image", p, s[:m.start()].count("\n") + 1)
    for m in re.finditer(r"pip3?\s+install\s+((?:[^\n\\]|\\\n)+)", s):
        args = m.group(1)
        ln = s[:m.start()].count("\n") + 1
        if re.search(r"\bpytest\b", args):
            cmd = s[max(0, m.start() - 200):m.end()]
            isolated = re.search(r"/opt/[\w.-]*verifier|/opt/venv|verifier[\w.-]*/bin/pip|"
                                 r"--target\s|--prefix\s", cmd)
            if isolated:
                r.N("TEST-DEPS-IN-IMAGE",
                    "verifier deps baked into an isolated prefix; correct for offline "
                    "grading, but confirm the agent's interpreter cannot see them", p, ln)
            else:
                r.M("TEST-DEPS-IN-IMAGE",
                    "test dependencies installed into the agent-visible environment; "
                    "move them to tests/test.sh", p, ln)
        # `-r requirements.txt` / `-c constraints.txt` defer pinning to that file
        if re.search(r"(^|\s)-(r|c)\s", args) or "--requirement" in args:
            continue
        # stop at the next shell command; anything after && or ; is not a package
        pkgs = re.split(r"&&|;|\|", args.replace("\\\n", " "))[0]
        for tok in pkgs.split():
            tok = tok.strip("\\'\"")
            if not tok or tok.startswith("-") or tok in ("pip", "pip3", "install"):
                continue
            if not re.search(r"(==|@|\bgit\+|\.whl$|\.tar\.gz$)", tok):
                r.M("UNPINNED", f"unpinned pip package: {tok}", p, ln)
                break
    if re.search(r"npm\s+install\s+(?!.*@\d)[a-z]", s):
        r.M("UNPINNED", "unpinned npm install", p)
    # apt is deliberately NOT checked: the platform guidelines make pinning high
    # severity "excluding apt", and the terminus reference Dockerfiles themselves
    # install apt packages unpinned. Language packages and the base image stay checked.
    if "privileged" in s:
        r.B("PRIVILEGED", "privileged mode requested", p)
    for u in NET.findall(s):
        if not NET_OK.search(u):
            r.M("NET-AT-RUNTIME", "non-package URL in the environment", p, evidence=u)
    if re.search(r"git\s+clone(?![^\n]*(--branch|checkout))", s):
        r.M("LEAK", "git clone without pinning to a commit", p)
    for f in glob.glob(f"{d}/environment/**/*", recursive=True):
        if os.path.isfile(f) and SECRET.search(read(f) or ""):
            r.B("SECRET", "credential-shaped string in the environment",
                os.path.relpath(f, d))


# ------------------------------------------------------------------ test.sh
def check_testsh(d, r):  # noqa: D103
    p = "tests/test.sh"
    s = read(f"{d}/{p}")
    if not s:
        return
    one = re.search(r"echo\s+1\s*>\s*\S*reward", s)
    zero = re.search(r"echo\s+0\s*>\s*\S*reward", s)
    if not (one and zero):
        r.B("NO-REWARD-FILE", "reward file not written on both branches", p)
    if not re.search(r'PWD"?\s*=\s*"?/"', s):
        r.M("NO-WORKDIR", "no WORKDIR guard", p)
    df = read(f"{d}/environment/Dockerfile")
    isolated_runner = bool(re.search(r"/opt/[\w.-]*verifier|/opt/venv", df + s))
    if not re.search(r"\buv(x|\s|_)|virtualenv|python -m venv", s) and not isolated_runner:
        r.M("RUNNER-NOT-PROVISIONED",
            "test.sh assumes the interpreter and packages are already in the image, and "
            "no isolated verifier prefix is set up either", p)
    for m in re.finditer(r"\$\{?([A-Z_][A-Z0-9_]*)\}?", s):
        v = m.group(1)
        if v in ("HOME", "PWD", "PATH", "USER", "SHELL", "HOSTNAME", "LANG"):
            continue
        if f"{v}:-" not in s and f"{v}=" not in s:
            r.M("ENV-NO-DEFAULT", f"${v} used with no default", p,
                s[:m.start()].count("\n") + 1)
            break
    if re.search(r"(oracle|ORACLE|IS_ORACLE|EVAL_IS_ORACLE)", s):
        r.B("ORACLE-ONLY-BRANCH",
            "test.sh appears to branch on oracle mode; conditions must be identical", p,
            lineno(s, "racle"))


# ----------------------------------------------------------------- solve.sh
def check_solve(d, r):
    p = "solution/solve.sh"
    s = read(f"{d}/{p}")
    if not s:
        return
    if not s.lstrip().startswith("#!"):
        r.M("NO-STRICT-MODE", "no shebang", p)
    if "set -euo pipefail" not in s:
        r.M("NO-STRICT-MODE", "solve.sh should run under `set -euo pipefail`", p)
    if re.search(r"^\s*(rm|sed -i|mv|cp)[^\n]*\btests?/", s, re.M):
        r.B("SUITE-EDITED", "solve.sh modifies the graded suite", p)
    for u in NET.findall(s):
        if not NET_OK.search(u):
            r.M("NET-AT-RUNTIME", "solution fetches over the network", p, evidence=u)
    if re.search(r"random\.|shuf\b|\$RANDOM|uuid", s) and not re.search(r"seed|SEED", s):
        r.M("NON-DETERMINISTIC-SOLUTION", "randomness without a seed", p)
    if re.search(r"\b(date|now\(\))\b", s) and "date +" in s:
        r.N("NON-DETERMINISTIC-SOLUTION", "wall-clock time in the solution", p)
    if re.search(r"\bls\b(?![^\n|]*\|\s*sort)", s):
        r.N("NON-DETERMINISTIC-SOLUTION", "unsorted `ls` output may vary", p)


# ----------------------------------------------------------- instruction.md
def check_instruction(d, r):
    p = "instruction.md"
    s = read(f"{d}/{p}")
    if not s:
        return
    if "canary" in s.lower():
        r.M("TEMPLATE-RESIDUE", "canary string present; outdated skeleton", p)
    paras = [x for x in re.split(r"\n\s*\n", s.strip()) if x.strip()]
    bullets = len(re.findall(r"^\s*[-*+]\s+", s, re.M))
    if len(paras) > 6 or bullets > 20:
        r.M("VERBOSE-INSTRUCTION",
            f"{len(paras)} blocks and {bullets} bullets; the bar is <=3 paragraphs "
            f"and <=20 bullets of requirements", p)
    for m in re.finditer(r"(?<![\w/`.$])((?:src|app|tests?|config|data|lib|bin|scripts)/[\w./-]+)",
                         s):
        r.M("RELATIVE-PATH", "instruction paths must be absolute", p,
            s[:m.start()].count("\n") + 1, m.group(1))
        break
    for pat in LLM_VOICE:
        m = re.search(pat, s)
        if m:
            r.M("GENERATED-VOICE", "instruction reads as model output", p,
                s[:m.start()].count("\n") + 1, m.group(0))
            break
    for pat in VAGUE:
        m = re.search(pat, s, re.I)
        if m:
            r.M("VAGUE-CRITERIA", "unverifiable success language", p,
                s[:m.start()].count("\n") + 1, m.group(0))
            break
    if re.search(r"[\U0001F300-\U0001FAFF☀-➿]", s):
        r.N("GENERATED-VOICE", "emoji in the instruction", p)
    if re.search(r"^\s*#{2,}\s*Step\s*\d", s, re.M | re.I):
        r.M("HINTS", "numbered step-by-step walkthrough", p)
    if re.search(r"(Hint|Detection Guidance|Look for:|Approach:)", s, re.I):
        r.M("HINTS", "a hints or guidance section", p, evidence=re.search(
            r"(Hint|Detection Guidance|Look for:|Approach:)", s, re.I).group(0))
    if re.search(r"def\s+\w+\([^)]*\)\s*->", s) or re.search(r"must export \w+ functions", s, re.I):
        r.M("PRESCRIPTIVE", "exact signatures given; state WHAT not HOW", p)
    if re.search(r"\buse (vim|emacs|nano)\b", s, re.I):
        r.M("UNVERIFIABLE-REQUIREMENT", "which editor was used cannot be graded", p)
    if re.search(r"\b(json|csv|yaml)\b", s, re.I) and not re.search(r"```|\{|\bfields?\b|\bcolumns?\b|\bschema\b", s, re.I):
        r.M("SCHEMA-UNSPECIFIED", "structured output required but no schema given", p)
    return s


# -------------------------------------------------------------------- tests
def check_tests(d, r, instruction=""):
    """Parsed with ast, so bodies and docstrings are exact rather than regex-guessed."""
    import ast
    p = "tests/test_outputs.py"
    src = read(f"{d}/{p}")
    if not src:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        r.B("SYNTAX", f"test suite does not parse: {e.msg}", p, e.lineno or 0)
        return []
    lines = src.splitlines()
    defs = {n.name: n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def asserts_in(fn, depth=0, seen=()):
        """Count assertions, following module-local helper calls one level deep.
        A test that delegates to `_run_and_expect_failure()` is not assertion-free."""
        n_a = sum(1 for n in ast.walk(fn)
                  if isinstance(n, ast.Assert)
                  or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                      and n.func.attr.startswith("assert"))
                  or isinstance(n, ast.Raise))
        if depth < 2:
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                   and n.func.id in defs and n.func.id not in seen:
                    n_a += asserts_in(defs[n.func.id], depth + 1, seen + (fn.name,))
        return n_a

    fns = [n for n in defs.values() if n.name.startswith("test")]
    skeleton, bodies = [], {}
    for fn in fns:
        body = "\n".join(lines[fn.lineno - 1:(fn.end_lineno or fn.lineno)])
        doc = ast.get_docstring(fn)
        asserts = asserts_in(fn) + len(re.findall(r"pytest\.raises", body))
        bodies[fn.name] = body
        skeleton.append({"name": fn.name, "line": fn.lineno,
                         "docstring": bool(doc), "assertions": asserts,
                         "lines": (fn.end_lineno or fn.lineno) - fn.lineno + 1})
        ln = fn.lineno
        if not doc:
            r.M("NO-DOCSTRING", f"{fn.name} has no docstring", p, ln)
        if re.fullmatch(r"test_(\d+|basic|works|main|simple|it|foo|bar)", fn.name):
            r.M("TEMPLATE-RESIDUE", f"uninformative test name {fn.name}", p, ln)
        if asserts == 0:
            r.M("VACUOUS", f"{fn.name} asserts nothing", p, ln)
        for n in ast.walk(fn):
            if isinstance(n, ast.Assert):
                t = n.test
                if isinstance(t, ast.Constant) and t.value in (True, 1):
                    r.M("VACUOUS", f"{fn.name}: assertion cannot fail", p, n.lineno)
                if asserts == 1 and isinstance(t, ast.Compare) \
                   and isinstance(t.comparators[0], ast.Constant) \
                   and t.comparators[0].value is None and isinstance(t.ops[0], ast.IsNot):
                    r.M("VACUOUS", f"{fn.name}: its only assertion is `is not None`", p, n.lineno)
                if isinstance(t, ast.Compare) and isinstance(t.ops[0], ast.Eq) \
                   and isinstance(t.comparators[0], ast.Constant) \
                   and isinstance(t.comparators[0].value, str) and len(t.comparators[0].value) > 40:
                    r.M("BRITTLE-ASSERT", f"{fn.name} compares a long output string exactly", p, n.lineno)
        if re.search(r"open\([^)]*\)\.read\(\)", body) and \
           re.search(r"assert[^\n]*[\"'][^\"']+[\"']\s+in\s+", body):
            r.M("IMPL-TEST", f"{fn.name} asserts on source text rather than behaviour", p, ln)
        if re.search(r"\b(latency|elapsed|duration|throughput|p50|p95|p99)\b", body, re.I) \
           and re.search(r"assert[^\n]*[<>]", body):
            r.B("LATENCY-TEST", f"{fn.name} asserts on timing; hardware-dependent", p, ln)
        if any(isinstance(n, ast.Global) for n in ast.walk(fn)):
            r.M("ORDER-DEPENDENT", f"{fn.name} uses global state", p, ln)
        if re.search(r"oracle", body, re.I) and re.search(r"\*\s*0\.9[5-9]", body):
            r.B("ORACLE-MIMICRY", f"{fn.name} thresholds within a few percent of the reference", p, ln)
    # near-duplicate bodies: strip literals and whitespace, then group
    norm = {}
    for name, body in bodies.items():
        k = re.sub(r"[\"'][^\"']*[\"']|\d+", "", re.sub(r"\s+", " ", body))
        if len(k) > 120:
            norm.setdefault(k, []).append(name)
    for names in norm.values():
        if len(names) > 2:
            r.M("CLONE-TESTS", f"{len(names)} near-identical bodies: {', '.join(names[:3])}...", p)
    if instruction:
        for f in sorted(set(re.findall(r"[\"'](/[\w./-]+\.\w+)[\"']", src))):
            if f not in instruction and not f.startswith("/logs"):
                r.M("FILE-UNNAMED", f"tests read {f}, never named in the instruction", p)
                break
    if len(fns) < 10:
        r.M("THIN-COVERAGE", f"{len(fns)} tests; the bar is more than 10", p)
    return skeleton


# ------------------------------------------------------------------- rubric
def check_rubric(d, r):
    p = next((n for n in ("rubric.txt", "rubrics.txt")
              if os.path.exists(f"{d}/{n}")), None)
    if not p:
        return {}
    s = read(f"{d}/{p}")
    pos = neg = 0
    for i, ln in enumerate(s.splitlines(), 1):
        t = ln.strip()
        if not t or t.startswith("#"):
            continue
        m = re.search(r",\s*([+-]?\d+)\s*$", t)
        if not m:
            r.M("RUBRIC-FORMAT", "line does not end in `, +N` or `, -N`", p, i, t)
            continue
        v = int(m.group(1))
        if abs(v) == 4:
            r.M("RUBRIC-FORMAT", "the value 4 is forbidden; use 1, 2, 3 or 5", p, i, t)
        if abs(v) not in (1, 2, 3, 5):
            r.M("RUBRIC-FORMAT", f"value {v} outside +/-1,2,3,5", p, i, t)
        if not t.startswith("Agent"):
            r.M("RUBRIC-FORMAT", "line must start with the word `Agent`", p, i, t)
        if re.search(r"\b(reads?|review(s|ed)?|understand|consider|is aware|inspects the (task|instruction))\b.*"
                     r"\b(instruction|task\.toml|prompt|readme)\b", t, re.I):
            r.M("RUBRIC-META", "criterion about reading the instruction is not engineering work", p, i, t)
        if re.search(r"\bruns? pytest\b|\bunit tests? pass\b", t, re.I):
            r.M("RUBRIC-META", "the suite runs automatically; do not grade it here", p, i, t)
        if v > 0:
            pos += v
        elif v < 0:
            neg += 1
    if neg < 3:
        r.M("RUBRIC-FORMAT", f"{neg} negative criteria; at least 3 are required", p)
    if not 10 <= pos <= 40:
        r.M("RUBRIC-FORMAT", f"positive total {pos}; the band is 10-40", p)
    return {"positive_total": pos, "negative_count": neg, "file": p}


# ------------------------------------------------------ difficulty floor
# Derived from the 51-task corpus with 816 measured rollouts. 62-64% of all
# model failures are near-misses concentrated on 1-2 discriminator tests, and
# those tests cluster into four capability classes (counts = tasks whose
# discriminators demand it): recompute/cross-artifact consistency (17),
# sequencing/recovery (17), fault-path rejection (10), variant/holdout (9).
# Every shipped task's suite exercises >=2 classes (or 1 + heavy execution
# dependence); trivially-easy suites exercise none. This is the deterministic
# floor for "can this task stumble a model" -- it does not rank difficulty
# beyond the floor (only rollouts do).
CAPABILITY_CLASSES = {
    "recompute_consistency": re.compile(
        r"independent|recomput|reconcil|matches?_|digest|fingerprint|cross[_-]?check|"
        r"consisten|seal|bound|integrity|checksum|hashlib|sha256|sha1|blake2|hmac|crc32", re.I),
    "variant_holdout": re.compile(
        r"variant|holdout|hidden|unseen|seed|generali[sz]|ablation|dynamic|hardcod|matrix|"
        r"ladder|parametri[sz]e|for\s+\w+\s+in\s+range\(|shuffle|random\.", re.I),
    "fault_rejection": re.compile(
        r"reject|denie|deny|fail|alarm|invalid|corrupt|poison|abort|tamper|stale|expired|"
        r"malformed|backdoor|pytest\.raises|assertRaises|returncode\s*!=\s*0|exit\s*code", re.I),
    "sequencing_recovery": re.compile(
        r"order|epoch|replay|recover|latch|idempot|resume|restart|race|concurren|multihop|"
        r"skew|offset|twice|second\s+run|re-?run|kill|sigterm", re.I),
}
EXEC_DEP = re.compile(r"subprocess|check_output|check_call|\brun\(|Popen|os\.system|\.sh\b|"
                      r"docker|make\b|cargo|npm|node\s|python3?\s", re.I)


def check_difficulty_floor(d, r):
    import ast as _ast
    hits, execdep = {}, 0
    tdir = os.path.join(d, "tests")
    for root, _, fs in os.walk(tdir) if os.path.isdir(tdir) else []:
        for fname in fs:
            if not fname.endswith(".py"):
                continue
            src = read(os.path.join(root, fname))
            try:
                tree = _ast.parse(src)
            except SyntaxError:
                continue
            lines = src.splitlines()
            for n in _ast.walk(tree):
                if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) \
                        and n.name.startswith("test"):
                    body = n.name + "\n" + "\n".join(
                        lines[n.lineno - 1:(n.end_lineno or n.lineno)])
                    for c, rx in CAPABILITY_CLASSES.items():
                        if rx.search(body):
                            hits[c] = hits.get(c, 0) + 1
                    if EXEC_DEP.search(body):
                        execdep += 1
    r.capability_classes = {**hits, "_execution_dependent": execdep}
    n_classes = len(hits)
    if not (n_classes >= 2 or (n_classes >= 1 and execdep >= 3)):
        missing = [c for c in CAPABILITY_CLASSES if c not in hits]
        r.B("DIFFICULTY-FLOOR",
            f"suite exercises {n_classes} capability class(es) "
            f"({', '.join(sorted(hits)) or 'none'}); the floor is two of: "
            "recompute/cross-artifact consistency, variant/holdout generalisation, "
            "fault-path rejection, sequencing/recovery. Add tests that force the "
            "missing behaviour -- e.g. " + ", ".join(missing[:2]),
            "tests/test_outputs.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="findings only, no skeleton")
    a = ap.parse_args()
    d = a.task.rstrip("/")
    r = Report()
    check_structure(d, r)
    meta = check_toml(d, r)
    check_docker(d, r)
    check_testsh(d, r)
    check_solve(d, r)
    instr = check_instruction(d, r) or ""
    skel = check_tests(d, r, instr)
    check_difficulty_floor(d, r)
    rub = check_rubric(d, r)
    counts = {s: sum(1 for f in r.f if f["severity"] == s)
              for s in ("BLOCKER", "MAJOR", "MINOR")}
    caps = getattr(r, "capability_classes", {})
    out = {"task": os.path.basename(d), "counts": counts, "findings": r.f,
           "capability_classes": caps,
           "rubric": rub, "instruction_words": len(instr.split()),
           "test_count": len(skel)}
    if not a.quiet:
        out["test_skeleton"] = skel
    if a.json:
        print(json.dumps(out, separators=(",", ":")))
    else:
        named = [k for k in caps if not k.startswith("_")]
        execdep = caps.get("_execution_dependent", "?")
        print(f"{out['task']}  BLOCKER {counts['BLOCKER']}  MAJOR {counts['MAJOR']}  "
              f"MINOR {counts['MINOR']}  | {len(skel)} tests, {out['instruction_words']}w "
              f"instruction, rubric +{rub.get('positive_total','?')}/{rub.get('negative_count','?')}neg"
              f"  | classes {','.join(named) or 'none'} execdep={execdep}")
        for f in r.f:
            loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            sv = {"BLOCKER": "BLOCK", "MAJOR": "MAJOR", "MINOR": "minor"}[f["severity"]]
            print(f"  {sv} {f['tag']:26s} {loc:34s} {f['what']}")
    return min(counts["BLOCKER"], 100)


if __name__ == "__main__":
    sys.exit(main())
