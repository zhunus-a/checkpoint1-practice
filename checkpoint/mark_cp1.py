#!/usr/bin/env python3
"""
INF 345 - Checkpoint 1 marker. Tuesday 27 October 2026.      THIS FILE IS THE RUBRIC.

Run it from the root of your repository (Linux, macOS or WSL; Python 3.9+, git, bash):

    python3 checkpoint/mark_cp1.py                  # marks your last COMMIT, not unsaved edits
    python3 checkpoint/mark_cp1.py --pr-body pr.md  # also checks a copy of your PR description

You do not have to run it. Your pipeline's log is the feedback that matters. After the
deadline the lecturer runs his own copy of this file on a GitHub machine. That run adds
two things you cannot check here: it looks for the log lines you quote in your
pipeline's real logs, and it builds your image with Docker.

HOW IT SCORES: four blocks of 25 points. Your repository has one fault in each block.

  15 points  the fix. Every rule of the block holds. The rules are in BLOCK_RULES
             below, and the output prints them.
  10 points  the diagnosis, in your pull request description, under the block's heading
             (### 1, ### 2, ### 3, ### 4). It names:
               - the step where you saw the fault (a step name from ci.yml),
               - one line copied from your pipeline's log, in backticks (the marker
                 checks that the line is really in your logs),
               - the file you changed.
             All three, plus at least 10 words of your own: 10 points. At least one of
             the three: 5 points. Nothing: 0. The diagnosis counts only once the fix counts.

  Gate: a credential anywhere in the history (any branch, any commit) scores 0.
  The exit code is 0 only at 100.

The marker runs its own copy of the tests, so editing tests/ changes nothing.
The rules that read ci.yml need PyYAML:  python3 -m pip install pyyaml
                                     or:  sudo apt install python3-yaml
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

try:
    import yaml
except ImportError:  # reported in the output; the rules that need it say NOT CHECKED
    yaml = None

VERSION = "cp1-2026-10-27"
FIX_POINTS, DIAG_POINTS = 15, 10
MIN_WORDS = 10        # words of the student's own in a diagnosis, outside backticks
MIN_QUOTE = 8         # non-space characters in a quoted log line ("TESTS: 5/6" has 9)

BLOCK_NAMES = {
    1: "The pipeline runs",
    2: "The pipeline tells the truth",
    3: "The service keeps the contract",
    4: "The image builds",
}

# What must be true. Every rule is checked whatever fault you were given.
BLOCK_RULES = {
    1: ["ci.yml is valid YAML, and a job in it has a step that runs scripts/test.sh",
        "that job checks out the repository before it runs scripts/test.sh",
        "scripts/test.sh and scripts/run.sh are committed as executable (mode 100755)",
        "scripts/test.sh and scripts/run.sh have Linux line endings (no \\r)"],
    2: ["with one failing test, scripts/test.sh exits non-zero and prints TESTS: 3/4",
        "with every test passing, scripts/test.sh exits 0 and prints TESTS: 4/4",
        "the step that runs scripts/test.sh passes its exit code on: no ||, no set +e, "
        "no continue-on-error, and a pipe only under shell: bash"],
    3: ["the checkpoint's own copy of tests/test_server.py passes against your src/ and "
        "scripts/run.sh: /healthz answers 200, $PORT is honoured, the server binds 0.0.0.0"],
    4: ["the image builds (with Docker; without Docker, estimated by reading the files)",
        "the image name the pipeline builds is lowercase: ${GITHUB_REPOSITORY,,}",
        "M3 image hygiene: a non-root USER; .dockerignore keeps out .git and .env; "
        "requirements.txt is installed before the source is copied",
        "the pipeline still builds the image (a step runs docker build)"],
}

# ---------------------------------------------------------------- the tests
# The generator ships exactly this file as tests/test_server.py, and block 3 runs
# this copy, never the one in your repository.

TESTS_PY = r'''"""The notes service against the M1 contract.

Checkpoint 1: the marker runs its OWN copy of this file, so editing it here never
changes your mark. Run the tests with:  ./scripts/test.sh
"""
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from server import make_server  # noqa: E402


def get(port, path, timeout=2.0):
    """GET a path. Returns (status, body). An error status is an answer too."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestNotesService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_root_answers(self):
        self.assertEqual(get(self.port, "/")[0], 200)

    def test_notes_counts_three(self):
        self.assertEqual(get(self.port, "/notes"), (200, "3"))

    def test_first_and_latest_note(self):
        self.assertEqual(get(self.port, "/notes/first"), (200, "alpha"))
        self.assertEqual(get(self.port, "/notes/latest"), (200, "gamma"))

    def test_healthz_is_ok(self):
        status, body = get(self.port, "/healthz")
        self.assertEqual(status, 200, "GET /healthz must answer 200 (the M1 contract)")
        self.assertEqual(body, "ok")

    def test_listens_on_all_interfaces(self):
        self.assertEqual(self.server.server_address[0], "0.0.0.0",
                         "bind 0.0.0.0 - on 127.0.0.1 nothing outside the container can connect")

    def test_run_sh_honours_port(self):
        port = free_port()
        env = dict(os.environ, PORT=str(port))
        proc = subprocess.Popen([os.path.join(ROOT, "scripts", "run.sh")], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        answer = None
        try:
            deadline = time.time() + 5
            while answer is None and time.time() < deadline:
                try:
                    answer = get(port, "/", timeout=1)
                except OSError:
                    time.sleep(0.2)
        finally:
            proc.terminate()
            proc.wait(timeout=5)
        self.assertIsNotNone(answer, f"with PORT={port}, nothing answered on port {port} "
                                     "(the M1 contract: scripts/run.sh honours $PORT)")


if __name__ == "__main__":
    unittest.main()
'''
N_TESTS = len(re.findall(r"^    def test_", TESTS_PY, re.M))

# Block 2 swaps tests/ for one of these, which never import your service, so it
# checks only what scripts/test.sh does with a failure.
_PROBE = '''import unittest


class Probe(unittest.TestCase):
    def test_one(self):
        self.assertTrue(True)

    def test_two(self):
        self.assertTrue(True)

    def test_three(self):
        self.assertTrue(True)

    def test_four(self):
        self.assertEqual(1, {value}, "a probe test")
'''
PROBE_PASS = _PROBE.format(value=1)
PROBE_FAIL = _PROBE.format(value=2)

TESTS_LINE = re.compile(r"^\s*TESTS:\s*(\d+)\s*/\s*(\d+)\s*$", re.M)
TEST_SH_CALL = re.compile(r"(?:^|[\s;&|(/])scripts/test\.sh(?![\w.])")


class MarkerError(Exception):
    pass


# =================================================================== helpers

def run(cmd, cwd=None, env=None, timeout=60, input_bytes=None):
    """Run a command; never raises. Returns (rc, output) with stderr merged."""
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, input=input_bytes, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace")
        return 124, out + f"\n[timed out after {timeout}s]"
    except OSError as e:
        return 127, str(e)


def git(repo, *args, timeout=120):
    rc, out = run(["git", "-C", repo, *args], timeout=timeout)
    if rc != 0:
        raise MarkerError(f"git {' '.join(args)} failed: {out.strip()[:300]}")
    return out


def read_tree(repo, rev):
    """{path: (mode, bytes)} for every file in a commit: the committed bytes and
    modes, exactly what a runner's checkout gets. No line-ending filters."""
    p = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "-z", rev],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise MarkerError(f"cannot read commit {rev}: {p.stderr.decode(errors='replace')[:200]}")
    entries = []
    for rec in p.stdout.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        if kind == "blob":
            entries.append((path.decode("utf-8", "replace"), mode, sha))
    blobs = {}
    if entries:
        req = "".join(sha + "\n" for _, _, sha in entries).encode()
        p = subprocess.run(["git", "-C", repo, "cat-file", "--batch"], input=req,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        data, pos = p.stdout, 0
        while pos < len(data):
            nl = data.index(b"\n", pos)
            sha, _, size = data[pos:nl].decode().split()
            start = nl + 1
            blobs[sha] = data[start:start + int(size)]
            pos = start + int(size) + 1
    return {path: (mode, blobs[sha]) for path, mode, sha in entries}


def write_tree(tree, dest, lf_scripts=False):
    """Write files to disk. lf_scripts: strip \\r from scripts/*.sh and make them
    executable, so a block other than block 1 is never failed by block 1's fault."""
    for path, (mode, data) in tree.items():
        parts = path.split("/")
        if path.startswith("/") or ".." in parts or mode == "120000":
            continue                                  # no symlinks, nothing outside dest
        full = os.path.join(dest, *parts)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        is_script = path.startswith("scripts/") and path.endswith(".sh")
        if lf_scripts and is_script:
            data = data.replace(b"\r\n", b"\n")
        with open(full, "wb") as f:
            f.write(data)
        executable = mode == "100755" or (lf_scripts and is_script)
        os.chmod(full, 0o755 if executable else 0o644)


def text(tree, path):
    item = tree.get(path)
    return None if item is None else item[1].decode("utf-8", "replace")


def docker_available():
    rc, _ = run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=30)
    return rc == 0


def run_student(argv, root, timeout, sandbox=None):
    """Run the student's code. With a sandbox image it runs in a throwaway container
    with no network and only this copy of the repository mounted, so it cannot touch
    the marker, the runner or the result."""
    if sandbox:
        name = "cp1-" + uuid.uuid4().hex[:12]
        cmd = ["docker", "run", "--rm", "--name", name, "--network", "none",
               "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp",
               "-e", "LANG=C.UTF-8", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "-e", "PYTHONUNBUFFERED=1", "-v", f"{root}:/w", "-w", "/w", sandbox, *argv]
        rc, out = run(cmd, timeout=timeout)
        if rc == 124:
            run(["docker", "kill", name], timeout=30)
        return rc, out
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
           "HOME": os.environ.get("HOME", "/tmp"), "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
    try:
        p = subprocess.Popen(argv, cwd=root, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as e:
        return 127, str(e)
    try:
        out, _ = p.communicate(timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        out, rc = b"[timed out after %ds]" % timeout, 124
    finally:
        if hasattr(os, "killpg"):
            try:
                os.killpg(p.pid, signal.SIGKILL)       # anything it left running
            except OSError:
                pass
        if p.poll() is None:
            p.kill()
    return rc, out.decode("utf-8", "replace")


def tail(output, n=6):
    lines = [ln for ln in output.strip().splitlines() if ln.strip()]
    return " | ".join(lines[-n:])[:400]


# ================================================================= workflows

def load_workflows(tree):
    """[(path, data, raw text, error)] for every workflow file."""
    found = []
    for path in sorted(tree):
        if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")):
            raw = text(tree, path)
            data, err = None, None
            if yaml is not None:
                try:
                    data = yaml.safe_load(raw)
                    if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
                        data, err = None, "it has no jobs: section"
                except yaml.YAMLError as e:
                    err = "not valid YAML: " + " ".join(str(e).split())[:200]
            found.append((path, data, raw, err))
    return found


def steps_of(job):
    steps = job.get("steps") if isinstance(job, dict) else None
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def test_steps(workflows):
    """(workflow, job, index, step) for every step whose run: calls scripts/test.sh."""
    out = []
    for _, wf, _, _ in workflows:
        if not wf:
            continue
        for job in wf["jobs"].values():
            for i, step in enumerate(steps_of(job)):
                if isinstance(step.get("run"), str) and TEST_SH_CALL.search(step["run"]):
                    out.append((wf, job, i, step))
    return out


def truthy(v):
    if isinstance(v, str):
        return v.strip().lower() not in ("", "false", "0")
    return bool(v)


def effective_shell(wf, job, step):
    for d in (step, (job.get("defaults") or {}).get("run") or {},
              (wf.get("defaults") or {}).get("run") or {}):
        if isinstance(d, dict) and d.get("shell"):
            return str(d["shell"]).strip()
    return ""                                   # GitHub's default: bash -e {0}, no pipefail


def step_names(workflows):
    """Every name a student might use for a step: step and job names, and the
    action behind a uses: step (actions/checkout, checkout)."""
    names = set()
    for _, wf, _, _ in workflows:
        if not wf:
            continue
        for key, job in wf["jobs"].items():
            if isinstance(job, dict):
                names.update([str(key), str(job.get("name") or "")])
            for step in steps_of(job):
                if step.get("name"):
                    names.add(str(step["name"]))
                if isinstance(step.get("uses"), str):
                    action = step["uses"].split("@")[0]
                    names.update([action, action.split("/")[-1]])
                if isinstance(step.get("run"), str) and not step.get("name"):
                    names.add("Run " + step["run"].strip().splitlines()[0])
    return {n.strip() for n in names if len(n.strip()) >= 4}


def code_lines(raw):
    """The non-comment lines of a YAML file."""
    return [ln for ln in raw.splitlines() if not ln.strip().startswith("#")]


# ================================================================ Dockerfile

def parse_dockerfile(raw):
    """[(line, INSTRUCTION, arguments)], continuation lines joined, comments dropped."""
    out, buf, start = [], "", None
    for n, line in enumerate(raw.replace("\r\n", "\n").split("\n"), 1):
        s = line.strip()
        if s.startswith("#") or (not s and not buf):
            continue
        if start is None:
            start = n
        if s.endswith("\\"):
            buf += s[:-1] + " "
            continue
        buf += s
        parts = buf.split(None, 1)
        if parts:
            out.append((start, parts[0].upper(), parts[1] if len(parts) > 1 else ""))
        buf, start = "", None
    if buf.strip():
        parts = buf.split(None, 1)
        out.append((start, parts[0].upper(), parts[1] if len(parts) > 1 else ""))
    return out


def final_stage(instrs):
    last = max([i for i, ins in enumerate(instrs) if ins[1] == "FROM"], default=0)
    return instrs[last:]


def copy_sources(args):
    """(sources, from_another_stage) of a COPY/ADD."""
    a = args.strip()
    if a.startswith("["):
        try:
            items = json.loads(a)
        except ValueError:
            items = []
    else:
        try:
            items = shlex.split(a)
        except ValueError:
            items = a.split()
    flags = [x for x in items if x.startswith("--")]
    items = [x for x in items if not x.startswith("--")]
    return [norm_path(x) for x in items[:-1]], any(f.startswith("--from") for f in flags)


def norm_path(p):
    p = p.strip()
    while p.startswith("./"):
        p = p[2:]
    p = p.strip("/")
    return p or "."


def _glob_rx(pattern):
    """A .dockerignore pattern as a regex (Go filepath.Match plus Docker's **)."""
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
            continue
        if pattern.startswith("**", i):
            out, i = out + ".*", i + 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        elif c == "[" and "]" in pattern[i + 1:]:
            j = pattern.index("]", i + 1)
            out += "[" + pattern[i + 1:j].replace("\\", "\\\\") + "]"
            i = j + 1
            continue
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")


def dockerignore(raw):
    """A function path -> excluded? The last matching line wins; ! re-includes;
    excluding a directory excludes everything under it."""
    rules = []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        neg = s.startswith("!")
        s = norm_path(s[1:] if neg else s)
        rules.append((neg, _glob_rx(s)))

    def excluded(path):
        parts = path.split("/")
        candidates = ["/".join(parts[:k]) for k in range(1, len(parts) + 1)]
        result = False
        for neg, rx in rules:
            if any(rx.match(c) for c in candidates):
                result = not neg
        return result
    return excluded


def is_root_user(value):
    return value.strip().split(":")[0].strip() in ("", "root", "0")


# ================================================================== the rules

class Ctx:
    """Everything the blocks need, read once."""

    def __init__(self, repo, rev, docker, sandbox, workdir):
        self.repo, self.rev, self.sandbox, self.workdir = repo, rev, sandbox, workdir
        self.tree = read_tree(repo, rev)
        self.workflows = load_workflows(self.tree)
        self.docker = docker
        self.skipped = []

    def copy(self, name, tests=None):
        """A fresh copy of the committed files, scripts made runnable (LF, +x);
        tests=text replaces tests/ with that single file."""
        dest = os.path.join(self.workdir, name)
        tree = dict(self.tree)
        if tests is not None:
            tree = {p: v for p, v in tree.items() if not p.startswith("tests/")}
        write_tree(tree, dest, lf_scripts=True)
        if tests is not None:
            os.makedirs(os.path.join(dest, "tests"), exist_ok=True)
            with open(os.path.join(dest, "tests", "test_server.py"), "w") as f:
                f.write(tests)
        return dest


def rule(ok, detail=""):
    return {"ok": ok, "detail": detail}


def block1(c):
    wfs = c.workflows
    if yaml is None:
        r_yaml = r_checkout = rule(None, "NOT CHECKED: PyYAML is not installed")
    else:
        bad = [f"{p}: {e}" for p, _, _, e in wfs if e]
        steps = test_steps(wfs)
        if not wfs:
            r_yaml = rule(False, "there is no workflow in .github/workflows/")
        elif bad:
            r_yaml = rule(False, "; ".join(bad))
        elif not steps:
            r_yaml = rule(False, "no step in any workflow runs scripts/test.sh")
        else:
            r_yaml = rule(True, f"the step '{steps[0][3].get('name', steps[0][3]['run'])}' "
                                "runs scripts/test.sh")
        if steps:
            _, job, idx, _ = steps[0]
            before = steps_of(job)[:idx]
            has = any(str(s.get("uses", "")).startswith("actions/checkout@") for s in before)
            r_checkout = rule(has, "actions/checkout comes before it" if has else
                              "no actions/checkout step before it: the runner starts with an "
                              "empty folder")
        else:
            r_checkout = rule(False, "no step runs scripts/test.sh")
    modes, crlf = [], []
    for s in ("scripts/test.sh", "scripts/run.sh"):
        item = c.tree.get(s)
        if item is None:
            modes.append(f"{s} is missing")
            continue
        if item[0] != "100755":
            modes.append(f"{s} is committed as {item[0]}")
        if b"\r" in item[1]:
            crlf.append(s)
    r_mode = rule(not modes, "; ".join(modes) or "both are 100755")
    r_crlf = rule(not crlf, (", ".join(crlf) + " contain(s) \\r (Windows line endings)")
                  if crlf else "no \\r")
    return [r_yaml, r_checkout, r_mode, r_crlf]


def run_probe(c, probe, name):
    root = c.copy(name, tests=probe)
    rc, out = run_student(["bash", "scripts/test.sh"], root, timeout=90, sandbox=c.sandbox)
    m = TESTS_LINE.findall(out)
    return rc, (f"{m[-1][0]}/{m[-1][1]}" if m else None), out


def block2(c):
    if "scripts/test.sh" not in c.tree:
        missing = rule(False, "scripts/test.sh is missing")
        return [missing, missing, missing]
    rc, line, out = run_probe(c, PROBE_FAIL, "probe-fail")
    ok = rc != 0 and line == "3/4"
    r_fail = rule(ok, f"exit {rc}, TESTS: {line or 'no TESTS line'}" + ("" if ok else
                  f" - it must exit non-zero and print TESTS: 3/4. Last lines: {tail(out)}"))
    rc, line, out = run_probe(c, PROBE_PASS, "probe-pass")
    ok = rc == 0 and line == "4/4"
    r_pass = rule(ok, f"exit {rc}, TESTS: {line or 'no TESTS line'}" + ("" if ok else
                  f" - it must exit 0 and print TESTS: 4/4. Last lines: {tail(out)}"))
    if yaml is None:
        return [r_fail, r_pass, rule(None, "NOT CHECKED: PyYAML is not installed")]
    problems = []
    for wf, job, _, step in test_steps(c.workflows):
        body = step["run"]
        if truthy(step.get("continue-on-error")) or truthy(job.get("continue-on-error")):
            problems.append("continue-on-error is set")
        if "||" in body:
            problems.append("|| swallows its exit code")
        if re.search(r"\bset\s+\+e\b", body):
            problems.append("set +e")
        if "|" in body.replace("||", "") and effective_shell(wf, job, step) != "bash":
            problems.append("a pipe without shell: bash (GitHub's default shell has no pipefail)")
    if not test_steps(c.workflows):       # block 1 reports that; one fault, one block
        return [r_fail, r_pass, rule(True, "no step runs scripts/test.sh (see block 1)")]
    r_step = rule(not problems, "; ".join(problems) or "it passes the exit code on")
    return [r_fail, r_pass, r_step]


def block3(c):
    if "src/server.py" not in c.tree:
        return [rule(False, "src/server.py is missing")]
    root = c.copy("contract", tests=TESTS_PY)
    rc, out = run_student(["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
                          root, timeout=120, sandbox=c.sandbox)
    ran = re.findall(r"^Ran (\d+) tests? in", out, re.M)
    ok = rc == 0 and ran and int(ran[-1]) == N_TESTS and re.search(r"^OK", out, re.M)
    if ok:
        return [rule(True, f"{N_TESTS}/{N_TESTS} of the checkpoint's tests pass")]
    failing = re.findall(r"^(?:FAIL|ERROR): (test\w+)", out, re.M)
    reasons = re.findall(r"^(\w*Error: .+)$", out, re.M)
    detail = ("failing: " + ", ".join(dict.fromkeys(failing))) if failing else "the tests did not pass"
    if reasons:
        detail += " | " + " | ".join(dict.fromkeys(r[:160] for r in reasons[:3]))
    elif not failing:
        detail += " | " + tail(out)
    return [rule(False, detail)]


def dockerfile_facts(c):
    raw = text(c.tree, "Dockerfile")
    if raw is None:
        return None
    stage = final_stage(parse_dockerfile(raw))
    req = pip = src = None
    users = []
    for i, (_, ins, args) in enumerate(stage):
        if ins in ("COPY", "ADD"):
            sources, other_stage = copy_sources(args)
            if other_stage:
                continue
            if req is None and any(s in ("requirements.txt", ".") for s in sources):
                req = i
            if src is None and any(s == "." or s == "src" or s.startswith("src/")
                                   for s in sources):
                src = i
        elif ins == "RUN" and pip is None and "pip" in args and "install" in args \
                and "requirements.txt" in args:
            pip = i
        elif ins == "USER":
            users.append((i, args.strip()))
    return {"stage": stage, "req": req, "pip": pip, "src": src, "users": users}


def estimate_build(c, facts):
    """Without Docker: the ways this Dockerfile can fail, read from the files."""
    excluded = dockerignore(text(c.tree, ".dockerignore"))
    problems = []
    for line, ins, args in facts["stage"]:
        if ins not in ("COPY", "ADD"):
            continue
        sources, other_stage = copy_sources(args)
        if other_stage:
            continue
        for s in sources:
            if s == "." or "://" in s:
                continue
            if any(ch in s for ch in "*?["):
                rx = _glob_rx(s)
                kept = [p for p in c.tree if rx.match(p) and not excluded(p)]
            else:
                kept = [p for p in c.tree if (p == s or p.startswith(s + "/")) and not excluded(p)]
            if not kept:
                problems.append(f'line {line}: {ins} {s} - "/{s}": not found (missing, or '
                                "excluded by .dockerignore)")
    if facts["pip"] is not None and (facts["req"] is None or facts["req"] > facts["pip"]):
        line = facts["stage"][facts["pip"]][0]
        problems.append(f"line {line}: pip install -r requirements.txt runs before "
                        "requirements.txt is copied in")
    users = facts["users"]
    if users and not is_root_user(users[-1][1]):
        after = [ln for i, (ln, ins, _) in enumerate(facts["stage"])
                 if ins == "RUN" and i > users[-1][0]]
        if after:
            problems.append(f"line {after[0]}: a RUN after USER {users[-1][1]} runs as that "
                            "user, who cannot write to directories root created")
    return problems


def real_build(c):
    root = os.path.join(c.workdir, "context")
    write_tree(c.tree, root)
    tag = "cp1-mark-" + uuid.uuid4().hex[:10]
    rc, out = run(["docker", "build", "--progress=plain", "--tag", tag, "."], cwd=root,
                  timeout=600)
    run(["docker", "image", "rm", "-f", tag], timeout=60)
    errors = [ln.strip() for ln in out.splitlines() if "ERROR" in ln or "error:" in ln.lower()]
    return rc == 0, (errors[-1][:300] if errors else tail(out))


def block4(c):
    facts = dockerfile_facts(c)
    if facts is None:
        missing = rule(False, "there is no Dockerfile")
        return [missing, missing, missing, missing]
    # 1. it builds
    if c.docker:
        ok, detail = real_build(c)
        r_build = rule(ok, "docker build succeeded" if ok else "docker build failed: " + detail)
    else:
        problems = estimate_build(c, facts)
        r_build = rule(not problems, "; ".join(problems) or
                       "no build error found by reading the files (no Docker here)")
        if c.docker is None:
            c.skipped.append({"name": "image build",
                              "detail": "Docker was not available: estimated from the files"})
    # 2. a lowercase image name
    raws = [(p, raw) for p, _, raw, _ in c.workflows]
    bad = []
    for path, raw in raws:
        for line in code_lines(raw):
            rest = re.sub(r"\$\{GITHUB_REPOSITORY,,\}", "", line)
            if re.search(r"GITHUB_REPOSITORY(?!_)", rest) or \
                    re.search(r"\$\{\{\s*github\.repository\s*\}\}", line):
                bad.append(line.strip())
            for ref in re.findall(r"ghcr\.io/[A-Za-z0-9._/-]+", line):
                if ref != ref.lower():
                    bad.append(ref)
    r_name = rule(not bad, ("not lowercased: " + " ; ".join(bad)[:300]) if bad else
                  "every image name is lowercase")
    # 3. hygiene, as M3 checks it
    hyg = []
    users = facts["users"]
    if not users:
        hyg.append("no USER: the container would run as root")
    elif is_root_user(users[-1][1]):
        hyg.append(f"USER {users[-1][1]} is root")
    excluded = dockerignore(text(c.tree, ".dockerignore"))
    if ".dockerignore" not in c.tree:
        hyg.append("there is no .dockerignore")
    else:
        for p in (".git", ".env"):
            if not excluded(p):
                hyg.append(f".dockerignore does not keep out {p}")
    if facts["pip"] is None:
        hyg.append("no RUN pip install -r requirements.txt")
    elif facts["req"] is None or facts["src"] is None or \
            not facts["req"] < facts["pip"] < facts["src"]:
        hyg.append("the order must be: COPY requirements.txt, RUN pip install, then COPY the "
                   "source")
    r_hyg = rule(not hyg, "; ".join(hyg) or "non-root USER, .dockerignore, dependencies first")
    # 4. the pipeline still builds it
    builds = any(re.search(r"docker (buildx )?build\b|docker/build-push-action", ln)
                 for _, raw in raws for ln in code_lines(raw))
    r_ci = rule(builds, "a step runs docker build" if builds else
                "no workflow step builds the image any more")
    return [r_build, r_name, r_hyg, r_ci]


# ================================================================ the gate

HIGH_CONFIDENCE = [                    # the same list as the M1 and M3 markers
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"gh[pousr]_[A-Za-z0-9]{36,}", "GitHub token"),
    (r"github_pat_[A-Za-z0-9_]{50,}", "GitHub fine-grained token"),
    (r"-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----", "private key"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
]
DOC_VALUES = re.compile(r"(?i)(EXAMPLE|wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY)")
FUZZY = [(r"(?i)\b(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*"
          r"['\"][^'\"\s]{12,}['\"]", "hardcoded credential")]
FUZZY_ALLOW = re.compile(
    r"(?i)(example|sample|placeholder|dummy|change[_-]?me|replace[_-]?me"
    r"|your[_\-\w]*|[_\-]here\b|xxx+|<[^>]+>|\$\{[^}]+\}|\bfake\b"
    r"|redacted|todo|test[_-]?token|secret[_-]?key[_-]?here)")


def gate_credentials(repo):
    """Every commit on every branch: a credential that was committed and later
    deleted is still in the history, and still has to be revoked."""
    rc, out = run(["git", "-C", repo, "log", "-p", "--all", "--no-color", "--no-ext-diff"],
                  timeout=180)
    if rc != 0:
        return False, "could not read the history: " + out.strip()[:200]
    hits = []
    for line in out.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for pat, label in HIGH_CONFIDENCE:
            m = re.search(pat, line)
            if m and not DOC_VALUES.search(m.group(0)):
                hits.append(f"{label}: {m.group(0)[:12]}...")
        for pat, label in FUZZY:
            m = re.search(pat, line)
            if m and not FUZZY_ALLOW.search(m.group(0)):
                hits.append(f"{label}: {m.group(0)[:40]}")
    if hits:
        return False, "credential in the history - " + "; ".join(sorted(set(hits))[:3])
    return True, "no credential in the history (all branches)"


# ============================================================== the diagnosis

HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]*(?:block[ \t]*)?([1-4])\b.*$", re.I | re.M)
COMMENT = re.compile(r"<!--.*?-->", re.S)
FENCE = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.S)
INLINE = re.compile(r"(`+)(.+?)\1")
LABEL = re.compile(r"(?im)^[\s>*+-]*\**\s*(step|log line|log|changed|fix|what i changed)"
                   r"\s*\**\s*:\s*\**")
WORD = re.compile(r"[^\W_]+", re.U)
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
GH_MARKERS = [("##[error]", "Error: "), ("##[warning]", "Warning: "), ("##[notice]", "Notice: "),
              ("##[group]", ""), ("##[endgroup]", ""), ("##[debug]", "")]


def norm(s):
    s = ANSI.sub("", s).translate(QUOTES)
    for a, b in GH_MARKERS:
        s = s.replace(a, b)
    return " ".join(s.split())


def load_logs(logs_dir):
    """Every line of every file under logs_dir, normalised. None = no logs given."""
    if not logs_dir:
        return None
    lines = []
    for base, _, files in os.walk(logs_dir):
        for name in sorted(files):
            with open(os.path.join(base, name), encoding="utf-8", errors="replace") as f:
                lines.extend(norm(ln) for ln in f.read().splitlines())
    return [ln for ln in lines if ln]


def sections(body):
    body = COMMENT.sub("", (body or "").replace("\r\n", "\n"))
    marks = list(HEADING.finditer(body))
    out = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        n = int(m.group(1))
        out[n] = out.get(n, "") + body[m.end():end] + "\n"
    return out


def quotes_in(section):
    found = []
    for fenced in FENCE.findall(section):
        found.extend(ln.strip() for ln in fenced.splitlines())
    rest = FENCE.sub(" ", section)
    found.extend(m.group(2).strip() for m in INLINE.finditer(rest))
    if not found:                       # forgot the backticks: take the "Log line:" text
        m = re.search(r"(?im)^[\s>*+-]*\**\s*log(?: line)?\s*\**\s*:\s*\**(.+)$", rest)
        if m:
            found.append(m.group(1).strip())
    return [q for q in found if len(q.replace(" ", "")) >= MIN_QUOTE]


def prose_of(section):
    s = FENCE.sub(" ", section)
    s = INLINE.sub(" ", s)
    return LABEL.sub(" ", s)


def mentions_file(section, path):
    for name in {path, path.rsplit("/", 1)[-1]}:          # scripts/test.sh, or test.sh
        if re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", section, re.I):
            return True
    return False


def diagnose(section, names, changed, logs):
    """Points for one block's diagnosis, and why."""
    if not section or not section.strip():
        return {"points": 0, "detail": "no text under this block's heading", "hash": None}
    words = len(WORD.findall(prose_of(section)))
    low = section.lower()
    step_ok = any(n.lower() in low for n in names)
    changed_ok = any(mentions_file(section, f) for f in changed)
    quotes = quotes_in(section)
    if not quotes:
        log_ok = False
    elif logs is None:
        log_ok = None                            # nothing to search here: not verified
    else:
        log_ok = any(norm(q) and any(norm(q) in ln for ln in logs) for q in quotes)
    parts = {"step": step_ok, "log line": log_ok is not False, "file": changed_ok}
    missing = [k for k, v in parts.items() if not v]
    if not missing and words >= MIN_WORDS:
        points = DIAG_POINTS
    elif any(parts.values()):
        points = DIAG_POINTS // 2
    else:
        points = 0
    why = []
    if not step_ok:
        why.append("names no step from ci.yml")
    if log_ok is False:
        why.append("no log line in backticks" if not quotes else
                   "the quoted line is not in your pipeline's logs")
    if log_ok is None:
        why.append("log line not verified here")
    if not changed_ok:
        why.append("names no file your pull request changed")
    if words < MIN_WORDS:
        why.append(f"{words} words of your own (at least {MIN_WORDS})")
    prose = " ".join(WORD.findall(prose_of(section).lower()))
    return {"points": points, "words": words,
            "detail": ("complete" if not why else "; ".join(why)),
            "hash": hashlib.sha1(prose.encode()).hexdigest()[:12] if words >= MIN_WORDS else None}


def base_of(repo, rev):
    """The checkpoint's own commit (trailer CP1-Base), else the first commit."""
    rc, out = run(["git", "-C", repo, "log", "-n1", "--format=%H", "--grep=^CP1-Base:", rev])
    if rc == 0 and out.strip():
        return out.strip()
    rc, out = run(["git", "-C", repo, "rev-list", "--max-parents=0", rev])
    return out.split()[0] if rc == 0 and out.split() else None


def changed_files(repo, base, rev):
    if not base:
        return []
    rc, out = run(["git", "-C", repo, "diff", "--name-only", "--no-renames", base, rev])
    return [ln.strip() for ln in out.splitlines() if ln.strip()] if rc == 0 else []


# ================================================================== marking

def mark(repo=".", rev="HEAD", pr_body=None, logs_dir=None, docker="auto", sandbox=None):
    """The whole rubric. Returns a dict (see --json)."""
    repo = os.path.abspath(repo)
    sha = git(repo, "rev-parse", "--verify", rev + "^{commit}").strip()
    use_docker = {"yes": True, "no": False}.get(docker)
    if docker == "auto":
        use_docker = docker_available()
    elif docker == "yes" and not docker_available():
        use_docker = None                       # asked for, not there: estimate, and say so
    workdir = tempfile.mkdtemp(prefix="cp1-mark-")
    try:
        c = Ctx(repo, sha, use_docker, sandbox, workdir)
        gate_ok, gate_detail = gate_credentials(repo)
        rules = {1: block1(c), 2: block2(c), 3: block3(c), 4: block4(c)}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    base = base_of(repo, sha)
    changed = changed_files(repo, base, sha)
    names = step_names(c.workflows)
    if base:
        try:
            names |= step_names(load_workflows(read_tree(repo, base)))
        except MarkerError:
            pass
    logs = load_logs(logs_dir)
    secs = sections(pr_body) if pr_body is not None else {}
    if pr_body is not None and logs is None:
        c.skipped.append({"name": "log lines", "detail": "no pipeline logs given: the quoted "
                                                         "lines were not verified"})
    seen, blocks = {}, []
    for n in (1, 2, 3, 4):
        checks = [dict(rule=BLOCK_RULES[n][i], **r) for i, r in enumerate(rules[n])]
        fix = FIX_POINTS if all(ch["ok"] is True for ch in checks) else 0
        if pr_body is None:
            d = {"points": 0, "detail": "not checked: no pull request description given",
                 "hash": None}
        elif fix == 0:
            d = {"points": 0, "detail": "counts once the fix counts", "hash": None}
        else:
            d = diagnose(secs.get(n, ""), names, changed, logs)
            if d["hash"] and d["hash"] in seen:
                d = dict(d, points=0, detail=f"the same text as block {seen[d['hash']]}")
            elif d["hash"]:
                seen[d["hash"]] = n
        failed = [ch["detail"] for ch in checks if ch["ok"] is not True]
        detail = "; ".join(failed) if failed else ""
        if fix and d["points"] < DIAG_POINTS:
            detail = f"diagnosis {d['points']}/{DIAG_POINTS}: {d['detail']}"
        blocks.append({"n": n, "name": f"{n} {BLOCK_NAMES[n]}", "fix": fix,
                       "diagnosis": d["points"], "points": fix + d["points"],
                       "checks": checks, "diag": d, "detail": detail})
    score = sum(b["points"] for b in blocks) if gate_ok else 0
    result = {"marker": VERSION, "rev": sha, "score": score,
              "gates": [{"name": "no credential in the history", "ok": gate_ok,
                         "detail": gate_detail}],
              "blocks": blocks, "skipped": c.skipped, "changed": changed,
              "pr_body_checked": pr_body is not None, "logs_checked": logs is not None,
              "docker": {True: "built", False: "not used", None: "unavailable"}[use_docker],
              "pyyaml": yaml is not None}
    result["report"] = report(result)
    return result


def report(r):
    mark_ = {True: "ok ", False: "NO ", None: "-- "}
    out = [f"INF 345 Checkpoint 1 - marker {r['marker']}",
           f"commit {r['rev'][:12]}   pull request description: "
           f"{'checked' if r['pr_body_checked'] else 'not given (use --pr-body FILE)'}   "
           f"image: {r['docker']}", ""]
    if not r["pyyaml"]:
        out += ["WARNING: PyYAML is not installed, so the rules that read ci.yml are NOT CHECKED.",
                "         python3 -m pip install pyyaml   (or: sudo apt install python3-yaml)", ""]
    g = r["gates"][0]
    out += [f"Gate  {'OK ' if g['ok'] else 'FAILED'}  {g['detail']}", ""]
    for b in r["blocks"]:
        out.append(f"Block {b['name']:<34} {b['points']:>2}/25   (fix {b['fix']}/{FIX_POINTS}, "
                   f"diagnosis {b['diagnosis']}/{DIAG_POINTS})")
        for ch in b["checks"]:
            out.append(f"   {mark_[ch['ok']]} {ch['rule']}")
            if ch["ok"] is not True:
                out.append(f"       -> {ch['detail']}")
        if r["pr_body_checked"] and b["fix"]:
            out.append(f"   diagnosis: {b['diag']['detail']}")
        out.append("")
    for s in r["skipped"]:
        out.append(f"NOT CHECKED  {s['name']}: {s['detail']}")
    if r["skipped"]:
        out.append("")
    if not r["gates"][0]["ok"]:
        out.append("SCORE: 0/100 - the gate failed. Revoke the credential first, then ask "
                   "the lecturer.")
    elif not r["pr_body_checked"]:
        fixes = sum(b["fix"] for b in r["blocks"])
        out.append(f"SCORE: {fixes}/100 so far - the fixes. The other 40 points are the "
                   "diagnoses in your pull request description (--pr-body FILE).")
    else:
        out.append(f"SCORE: {r['score']}/100")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="INF 345 Checkpoint 1 marker (the rubric)")
    ap.add_argument("--repo", default=".", help="the repository (default: here)")
    ap.add_argument("--rev", default="HEAD", help="the commit to mark (default: HEAD)")
    ap.add_argument("--pr-body", help="a file holding your pull request description")
    ap.add_argument("--logs", help="a folder of your pipeline's logs (the official run)")
    ap.add_argument("--docker", choices=["auto", "yes", "no"], default="auto",
                    help="build the image for real (auto: if Docker is running)")
    ap.add_argument("--sandbox", metavar="IMAGE",
                    help="run your code inside this image, with no network (official run)")
    ap.add_argument("--json-out", metavar="FILE", help="also write the result as JSON")
    a = ap.parse_args(argv)
    try:
        body = None
        if a.pr_body:
            with open(a.pr_body, encoding="utf-8", errors="replace") as f:
                body = f.read()
        r = mark(a.repo, a.rev, body, a.logs, a.docker, a.sandbox)
    except MarkerError as e:
        print(f"marker: {e}", file=sys.stderr)
        return 2
    rc, st = run(["git", "-C", a.repo, "status", "--porcelain", "--untracked-files=no"])
    print(r["report"])
    if rc == 0 and st.strip() and a.rev == "HEAD":
        print("\nNote: you have uncommitted changes. The marker (and your pipeline) see only "
              "what is committed.")
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=1)
    return 0 if r["score"] == 100 else 1


if __name__ == "__main__":
    sys.exit(main())
