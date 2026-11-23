#!/usr/bin/env python3
"""Behavior tests of the bulk issue helpers (issue_bulk.py, run_state.py).

Only external gh I/O is replaced: a fake gh answers from a JSON fixture file and
logs every call. git is real and runs against temporary repositories with a
bare origin. No test needs network access or a model.
"""

import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "review/core/scripts"
FIXTURES = ROOT / "tests/fixtures/issue-bulk"
BULK = SCRIPTS / "issue_bulk.py"
STATE = SCRIPTS / "run_state.py"
REPO = "acme/widgets"
sys.path.insert(0, str(SCRIPTS))


# The fake gh matches each call against fixture rules in order: every "match"
# substring must occur in the argv (joined by \x1f) and no "absent" substring may.
# A rule with "once" is consumed when used. Calls are logged with any --input or
# --body-file content, so tests can assert exactly what would have been sent.
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
entry = {"args": args}
for flag, key in (("--input", "input"), ("--body-file", "body_file")):
    if flag in args:
        entry[key] = Path(args[args.index(flag) + 1]).read_text()
with open(os.environ["BULK_TEST_LOG"], "a") as handle:
    handle.write(json.dumps(entry) + "\n")
path = Path(os.environ["BULK_TEST_FIXTURE"])
fixture = json.loads(path.read_text())
joined = "\x1f".join(args)
for index, rule in enumerate(fixture.get("rules", [])):
    if not all(m in joined for m in rule.get("match", [])):
        continue
    if any(m in joined for m in rule.get("absent", [])):
        continue
    if rule.get("once"):
        fixture["rules"].pop(index)
        path.write_text(json.dumps(fixture))
    out = rule.get("stdout")
    if out is None and "file" in rule:
        out = Path(rule["file"]).read_text()
    elif out is not None and not isinstance(out, str):
        out = json.dumps(out)
    if out:
        sys.stdout.write(out if out.endswith("\n") else out + "\n")
    if rule.get("stderr"):
        sys.stderr.write(rule["stderr"] + "\n")
    sys.exit(rule.get("exit", 0))
sys.stderr.write("fake gh: unexpected call " + json.dumps(args) + "\n")
sys.exit(1)
'''

# Project tools that a fix must never run; each call leaves a marker file.
FAKE_TOOL = r'''#!/bin/sh
echo "$0 $*" >> "$BULK_TEST_FORBIDDEN"
exit 0
'''


def git(cwd, *args, check=True):
    # The tests' own git calls never run hooks, so the hook log only shows calls made by the helper.
    result = subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, *args], cwd=cwd, capture_output=True,
                            text=True)
    if check and result.returncode:
        raise AssertionError("git " + " ".join(args) + " failed: " + result.stderr)
    return result.stdout


class BulkTestCase(unittest.TestCase):
    """Shared temp layout: bin/ with fake gh, a git config, and helper runners."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(os.path.realpath(self.tmp.name))
        self.bin = self.base / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        for tool in ("make", "npm", "pytest", "go", "cargo"):
            path = self.bin / tool
            path.write_text(FAKE_TOOL)
            path.chmod(0o755)
        self.log = self.base / "gh-calls.jsonl"
        self.log.write_text("")
        self.fixture = self.base / "gh-fixture.json"
        self.forbidden = self.base / "forbidden-calls.log"
        gitconfig = self.base / "gitconfig"
        gitconfig.write_text("[user]\n\tname = Maintainer\n\temail = maintainer@example.com\n"
                             "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n")
        self.state_home = self.base / "state-home"
        home = self.base / "home"
        home.mkdir()
        # Isolated from the host: no inherited GIT_* variables, a private HOME and config directory, and git
        # never searches above the temporary directory for a repository.
        clean = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env = dict(clean, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        BULK_TEST_LOG=str(self.log), BULK_TEST_FIXTURE=str(self.fixture),
                        BULK_TEST_FORBIDDEN=str(self.forbidden), HOME=str(home),
                        XDG_CONFIG_HOME=str(home / ".config"), GIT_CEILING_DIRECTORIES=str(self.base.parent),
                        GIT_CONFIG_GLOBAL=str(gitconfig), GIT_CONFIG_NOSYSTEM="1",
                        XDG_STATE_HOME=str(self.state_home), TMPDIR=str(self.base / "tmp"))
        (self.base / "tmp").mkdir()
        keys = set(self.env) | {key for key in os.environ if key.startswith("GIT_")}
        self.saved_env = {key: os.environ.get(key) for key in keys
                          if key.startswith("GIT_") or key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME")}
        for key in self.saved_env:
            if key in self.env:
                os.environ[key] = self.env[key]
            else:
                os.environ.pop(key, None)
        self.addCleanup(self.restore_env)
        # Most tests play several sessions in a row (S1, then a resumed S2); a real resume comes after the lock
        # expired. Lock tests turn this off to see the refusal.
        self.expire_session_locks = True
        self.gh_rules([])

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def gh_rules(self, rules):
        self.fixture.write_text(json.dumps({"rules": rules}))
        self.log.write_text("")

    def gh_calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def run_script(self, script, *args, cwd=None):
        return subprocess.run([sys.executable, "-B", str(script), *map(str, args)],
                              cwd=str(cwd or self.base), env=self.env,
                              capture_output=True, text=True)

    def bulk(self, *args, cwd=None):
        if self.expire_session_locks and "--session" in args:
            self.expire_lock(args)
        return self.run_script(BULK, *args, cwd=cwd)

    def expire_lock(self, args):
        session = str(args[list(args).index("--session") + 1])
        for arg in args:
            lock = Path(str(arg)) / "lock"
            if lock.is_file():
                current = json.loads(lock.read_text())
                if current.get("session") != session:
                    lock.write_text(json.dumps(dict(current, updated_at="2000-01-01T00:00:00Z")))

    def bulk_ok(self, *args, cwd=None):
        result = self.bulk(*args, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def make_repo(self, name="work", origin_url=None):
        """A checkout with one commit on main, pushed to a bare origin."""
        bare = self.base / (name + "-origin.git")
        work = self.base / name
        git(self.base, "init", "--bare", "-b", "main", str(bare))
        git(self.base, "init", "-b", "main", str(work))
        (work / "README.md").write_text("widgets\n")
        (work / "src").mkdir()
        (work / "src/app.py").write_text("".join("line %d\n" % i for i in range(1, 51)))
        git(work, "add", "-A")
        git(work, "commit", "-m", "initial")
        git(work, "remote", "add", "origin", str(bare))
        git(work, "push", "-q", "origin", "main")
        if origin_url:
            git(work, "remote", "set-url", "origin", origin_url)
        return work, bare


class HarnessTests(BulkTestCase):
    def test_fake_gh_answers_by_rule_and_logs_calls(self):
        self.gh_rules([{"match": ["api", "user"], "stdout": {"login": "maint"}, "once": True}])
        result = subprocess.run(["gh", "api", "user"], env=self.env, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), {"login": "maint"})
        again = subprocess.run(["gh", "api", "user"], env=self.env, capture_output=True, text=True)
        self.assertEqual(again.returncode, 1)
        self.assertEqual([c["args"] for c in self.gh_calls()], [["api", "user"]] * 2)

    def test_repository_has_bare_origin(self):
        work, bare = self.make_repo()
        self.assertEqual(git(work, "ls-remote", "--heads", "origin").split()[-1], "refs/heads/main")
        self.assertEqual(git(work, "status", "--porcelain"), "")


class RunStateTests(BulkTestCase):
    def setUp(self):
        super().setUp()
        self.rs = load("run_state")
        self.root = self.base / "state-root"

    def test_init_creates_running_state_and_ignore_file(self):
        run_dir = Path(self.rs.init(str(self.root), "issue", REPO, "maint", {"limit": 10}, {"x": 1}))
        state = json.loads((run_dir / "state.json").read_text())
        self.assertEqual((state["schema_version"], state["kind"], state["status"]), (1, "issue", "running"))
        self.assertEqual((state["repository"], state["user"], state["options"], state["extra"]),
                         (REPO, "maint", {"limit": 10}, {"x": 1}))
        self.assertEqual(state["items"], {})
        self.assertRegex(state["run_id"], r"^[0-9]{8}-[0-9]{6}-issue(-[0-9]+)?$")
        self.assertEqual(run_dir.name, state["run_id"])
        self.assertFalse((self.root / ".gitignore").exists())

    def test_run_id_collision_adds_suffix(self):
        from datetime import datetime, timezone
        moment = datetime(2026, 11, 23, 9, 0, 0, tzinfo=timezone.utc)
        first = Path(self.rs.init(str(self.root), "issue", REPO, "m", {}, {}, now=moment))
        second = Path(self.rs.init(str(self.root), "issue", REPO, "m", {}, {}, now=moment))
        third = Path(self.rs.init(str(self.root), "issue", REPO, "m", {}, {}, now=moment))
        self.assertEqual(first.name, "20261123-090000-issue")
        self.assertEqual(second.name, "20261123-090000-issue-2")
        self.assertEqual(third.name, "20261123-090000-issue-3")
        for run in (first, second, third):
            self.assertRegex(run.name, r"^[0-9]{8}-[0-9]{6}-issue(-[0-9]+)?$")

    def test_update_is_atomic_and_exception_leaves_state(self):
        run_dir = self.rs.init(str(self.root), "issue", REPO, "m", {}, {}, items={7: {"phase": "selected"}})
        before = (Path(run_dir) / "state.json").read_text()

        def broken(state):
            state["items"]["7"]["phase"] = "half"
            raise RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            self.rs.update(run_dir, broken)
        self.assertEqual((Path(run_dir) / "state.json").read_text(), before)
        self.assertEqual(sorted(p.name for p in Path(run_dir).iterdir()), ["state.json"])
        self.rs.set_item(run_dir, 7, phase="collected")
        self.assertEqual(self.rs.load(run_dir)["items"]["7"]["phase"], "collected")
        self.assertEqual(sorted(p.name for p in Path(run_dir).iterdir()), ["state.json"])

    def test_find_unfinished_returns_running_runs_of_kind_newest_first(self):
        from datetime import datetime, timezone
        old = self.rs.init(str(self.root), "issue", REPO, "m", {}, {},
                           now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        new = self.rs.init(str(self.root), "issue", REPO, "m", {}, {},
                           now=datetime(2026, 2, 1, tzinfo=timezone.utc))
        done = self.rs.init(str(self.root), "issue", REPO, "m", {}, {},
                            now=datetime(2026, 3, 1, tzinfo=timezone.utc))
        self.rs.set_status(done, "finished")
        gone = self.rs.init(str(self.root), "issue", REPO, "m", {}, {},
                            now=datetime(2026, 4, 1, tzinfo=timezone.utc))
        self.rs.set_status(gone, "abandoned")
        self.rs.init(str(self.root), "pr", REPO, "m", {}, {},
                     now=datetime(2026, 5, 1, tzinfo=timezone.utc))
        runs = self.rs.find_unfinished(str(self.root), "issue")
        self.assertEqual([r["run_dir"] for r in runs], [new, old])

    def test_cli_find_unfinished_and_abandon(self):
        state_root = self.state_home / "cc-review/issue-bulk/acme__widgets"
        run_dir = self.rs.init(str(state_root), "issue", REPO, "m", {}, {})
        run_id = Path(run_dir).name
        listed = self.run_script(STATE, "find-unfinished", "--kind", "issue", "--repo", REPO)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual([r["run_id"] for r in json.loads(listed.stdout)["runs"]], [run_id])
        one = self.run_script(STATE, "find-unfinished", "--kind", "issue", "--repo", REPO, run_id)
        self.assertEqual(json.loads(one.stdout)["run_dir"], run_dir)
        latest = self.run_script(STATE, "find-unfinished", "--kind", "issue", "--repo", REPO, "--latest")
        self.assertEqual(json.loads(latest.stdout)["run_id"], run_id)
        missing = self.run_script(STATE, "find-unfinished", "--kind", "issue", "--repo", REPO,
                                  "20200101-000000-issue")
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(missing.stderr.strip(), "Error: no unfinished issue run '20200101-000000-issue'; "
                                                 "unfinished runs: " + run_id)
        abandon = self.run_script(STATE, "abandon", run_dir)
        self.assertEqual(abandon.returncode, 0, abandon.stderr)
        self.assertEqual(self.rs.load(run_dir)["status"], "abandoned")
        none = self.run_script(STATE, "find-unfinished", "--kind", "issue", "--repo", REPO, "x")
        self.assertEqual(none.stderr.strip(), "Error: no unfinished issue run 'x'; unfinished runs: none")
        shown = self.run_script(STATE, "show", run_dir)
        self.assertEqual(json.loads(shown.stdout)["status"], "abandoned")

    def test_root_is_per_user_even_inside_a_matching_checkout(self):
        work, _ = self.make_repo(origin_url="https://github.com/acme/widgets.git")
        expected = str(self.state_home / "cc-review/issue-bulk/acme__widgets")
        for cwd in (work / "src", self.base):
            with self.subTest(cwd=cwd):
                out = self.run_script(STATE, "root", "--kind", "issue", "--repo", REPO, cwd=cwd)
                self.assertEqual(json.loads(out.stdout)["root"], expected)
        run_dir = self.rs.init(expected, "issue", REPO, "m", {}, {})
        self.assertFalse(run_dir.startswith(str(work)))
        self.assertEqual(git(work, "status", "--porcelain", "--untracked-files=all"), "")
        bad = self.run_script(STATE, "root", "--kind", "issue", "--repo", "bad")
        self.assertEqual(bad.returncode, 1)

    def test_same_second_runs_sort_by_numeric_suffix(self):
        from datetime import datetime, timezone
        moment = datetime(2026, 11, 23, 9, 0, 0, tzinfo=timezone.utc)
        dirs = [self.rs.init(str(self.root), "issue", REPO, "m", {}, {}, now=moment) for _ in range(10)]
        runs = self.rs.find_unfinished(str(self.root), "issue")
        self.assertEqual(runs[0]["run_id"], "20261123-090000-issue-10")
        self.assertEqual(runs[-1]["run_id"], "20261123-090000-issue")
        self.assertEqual(len(runs), len(dirs))

    def test_unreadable_runs_are_reported(self):
        state_root = self.state_home / "cc-review/issue-bulk/acme__widgets"
        good = Path(self.rs.init(str(state_root), "issue", REPO, "m", {}, {}))
        broken = state_root / "20200101-000000-issue"
        broken.mkdir()
        (broken / "state.json").write_text("{not json")
        listed = json.loads(self.run_script(STATE, "find-unfinished", "--kind", "issue", "--repo", REPO).stdout)
        self.assertEqual([r["run_id"] for r in listed["runs"]], [good.name])
        self.assertEqual([Path(u["run_dir"]).name for u in listed["unreadable"]], [broken.name])
        missing = self.run_script(STATE, "find-unfinished", "--kind", "issue", "--repo", REPO, "20200102-000000-issue")
        self.assertIn("unreadable runs: 20200101-000000-issue", missing.stderr)

    def test_latest_without_any_run(self):
        out = self.run_script(STATE, "find-unfinished", "--kind", "issue", "--repo", REPO, "--latest")
        self.assertEqual(out.returncode, 1)
        self.assertEqual(out.stderr.strip(), "Error: no unfinished issue run; unfinished runs: none")

    def test_session_lock_refuses_then_allows_takeover(self):
        from datetime import datetime, timedelta, timezone
        run_dir = self.rs.init(str(self.root), "issue", REPO, "m", {}, {})
        start = datetime(2026, 11, 23, 9, 0, 0, tzinfo=timezone.utc)
        self.rs.claim_session(run_dir, "A", now=start)
        self.rs.claim_session(run_dir, "A", now=start + timedelta(minutes=10))
        with self.assertRaises(self.rs.StateError) as refused:
            self.rs.claim_session(run_dir, "B", now=start + timedelta(minutes=39))
        self.assertIn("in use by another session", str(refused.exception))
        self.assertIn("2026-11-23T09:40:00Z", str(refused.exception))
        self.rs.claim_session(run_dir, "B", now=start + timedelta(minutes=41))
        lock = json.loads((Path(run_dir) / "lock").read_text())
        self.assertEqual(lock, {"session": "B", "updated_at": "2026-11-23T09:41:00Z"})


def search_rules(fail_page2=False):
    page2 = {"match": ["BulkIssueSearch", "after=CURSOR1"], "file": str(FIXTURES / "page2.json")}
    if fail_page2:
        page2 = {"match": ["BulkIssueSearch", "after=CURSOR1"], "stderr": "HTTP 502: Bad Gateway", "exit": 1}
    return [{"match": ["BulkIssueSearch"], "absent": ["after="], "file": str(FIXTURES / "page1.json")}, page2]


def fixture_nodes():
    nodes = []
    for name in ("page1.json", "page2.json"):
        nodes.extend(json.loads((FIXTURES / name).read_text())["data"]["search"]["nodes"])
    # Classification-only nodes (not on a search page, so paging counts stay as they are).
    nodes.extend(json.loads((FIXTURES / "classify-extra.json").read_text())["nodes"])
    return nodes


class SelectionTests(BulkTestCase):
    def test_classify_every_fixture_node(self):
        bulk = load("issue_bulk")
        expected = json.loads((FIXTURES / "expected.json").read_text())
        seen = set()
        for node in fixture_nodes():
            if node["number"] in seen:
                continue
            seen.add(node["number"])
            want = expected[str(node["number"])]
            with self.subTest(issue=node["number"]):
                got = bulk.classify(node, REPO)
                self.assertEqual(got["reason"], want["reason"])
                self.assertEqual(got["pr"], want["pr"])
                if want["reason"] is None:
                    self.assertEqual([p["number"] for p in got["linked_prs"]], want["linked_prs"])
        self.assertEqual(len(seen), len(expected))

    def test_linked_pr_records(self):
        bulk = load("issue_bulk")
        nodes = {n["number"]: n for n in fixture_nodes()}
        open_pr = bulk.classify(nodes[130], REPO)["linked_prs"][0]
        self.assertEqual(open_pr, {"number": 505, "url": "https://github.com/acme/widgets/pull/505",
                                   "state": "OPEN", "merged": False, "author": "newcomer",
                                   "maintainer_owned": False, "open_non_maintainer": True})
        closed = bulk.classify(nodes[129], REPO)["linked_prs"][0]
        self.assertEqual((closed["state"], closed["maintainer_owned"], closed["open_non_maintainer"]),
                         ("CLOSED", True, False))
        unmerged = bulk.classify(nodes[132], REPO)["linked_prs"][0]
        self.assertEqual((unmerged["maintainer_owned"], unmerged["open_non_maintainer"]), (True, False))
        self.assertEqual(bulk.classify(nodes[134], REPO.upper())["reason"], "maintainer_pr")
        bot = bulk.classify(nodes[203], REPO)["linked_prs"][0]
        self.assertEqual((bot["maintainer_owned"], bot["open_non_maintainer"]), (False, True))
        merged = bulk.classify(nodes[204], REPO)["linked_prs"][0]
        self.assertEqual((merged["merged"], merged["maintainer_owned"], merged["open_non_maintainer"]),
                         (True, False, False))

    def test_own_pr_is_ignored_only_by_recorded_url_or_own_head_repository(self):
        bulk = load("issue_bulk")
        def own(head_repo, url="https://github.com/acme/widgets/pull/601"):
            return {"__typename": "PullRequest", "number": 601, "url": url, "state": "OPEN", "merged": False,
                    "headRefName": "cc-review/fix-issue-5", "authorAssociation": "OWNER",
                    "author": {"login": "maint", "__typename": "User"}, "baseRepository": {"nameWithOwner": REPO},
                    "headRepository": {"nameWithOwner": head_repo},
                    "reviews": {"pageInfo": {"hasPreviousPage": False}, "nodes": []},
                    "comments": {"pageInfo": {"hasPreviousPage": False}, "nodes": []}}
        pushed = {"pr_url": None, "branch": "cc-review/fix-issue-5", "user": "maint", "repository": REPO}
        node = lambda pr: recheck_node(5, timeline=[{"__typename": "CrossReferencedEvent", "source": pr}])
        self.assertIsNone(bulk.classify(node(own(REPO)), REPO, ignore=pushed)["reason"])
        self.assertEqual(bulk.classify(node(own("maint/widgets")), REPO, ignore=pushed)["reason"], "maintainer_pr")
        opened = dict(pushed, pr_url="https://github.com/acme/widgets/pull/601")
        self.assertIsNone(bulk.classify(node(own(REPO)), REPO, ignore=opened)["reason"])
        other = own(REPO, url="https://github.com/acme/widgets/pull/602")
        self.assertEqual(bulk.classify(node(other), REPO, ignore=opened)["reason"], "maintainer_pr")

    def pr_node(self, number=700, association="MEMBER", state="OPEN", truncated=False, head="topic"):
        page = {"hasPreviousPage": truncated}
        return {"__typename": "PullRequest", "number": number, "url": "https://github.com/acme/widgets/pull/%d"
                % number, "state": state, "merged": False, "headRefName": head, "authorAssociation": association,
                "author": {"login": "member1", "__typename": "User"}, "baseRepository": {"nameWithOwner": REPO},
                "reviews": {"totalCount": 0, "pageInfo": page, "nodes": []},
                "comments": {"totalCount": 0, "pageInfo": {"hasPreviousPage": False}, "nodes": []}}

    def test_disconnect_keeps_a_cross_reference(self):
        bulk = load("issue_bulk")
        pr = self.pr_node()
        events = [{"__typename": "CrossReferencedEvent", "source": pr},
                  {"__typename": "ConnectedEvent", "source": pr, "subject": {"__typename": "Issue"}},
                  {"__typename": "DisconnectedEvent", "source": pr, "subject": {"__typename": "Issue"}}]
        self.assertEqual(bulk.classify(recheck_node(5, timeline=events), REPO)["reason"], "maintainer_pr")
        only_link = events[1:]
        self.assertIsNone(bulk.classify(recheck_node(5, timeline=only_link), REPO)["reason"])

    def test_truncated_history_of_closed_pr_does_not_skip(self):
        bulk = load("issue_bulk")
        closed = self.pr_node(association="NONE", state="CLOSED", truncated=True)
        node = recheck_node(5, timeline=[{"__typename": "CrossReferencedEvent", "source": closed}])
        self.assertIsNone(bulk.classify(node, REPO)["reason"])
        open_pr = self.pr_node(association="NONE", truncated=True)
        node = recheck_node(5, timeline=[{"__typename": "CrossReferencedEvent", "source": open_pr}])
        self.assertEqual(bulk.classify(node, REPO)["reason"], "history_too_long")

    def test_truncated_or_missing_timeline_and_comments(self):
        bulk = load("issue_bulk")
        node = recheck_node(5, timeline=[{"__typename": "CrossReferencedEvent",
                                          "source": self.pr_node(association="NONE")}])
        node["timelineItems"]["pageInfo"]["hasPreviousPage"] = True
        self.assertEqual(bulk.classify(node, REPO)["reason"], "history_too_long")
        for key in ("comments", "timelineItems"):
            with self.subTest(missing=key):
                node = recheck_node(5)
                node[key] = None
                self.assertEqual(bulk.classify(node, REPO)["reason"], "history_too_long")

    def test_ceiling_on_a_page_boundary_is_not_exhausted(self):
        self.gh_rules(search_rules())
        result, out = self.select("--limit", "20", "--scan", "20")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual((summary["scanned"], summary["ceiling_reached"], summary["exhausted"]), (20, True, False))
        self.assertEqual(len(self.gh_calls()), 1)

    def test_search_capped_at_1000_results_is_not_exhausted(self):
        page = json.loads((FIXTURES / "page2.json").read_text())
        page["data"]["search"]["issueCount"] = 4000
        page["data"]["search"]["pageInfo"] = {"hasNextPage": False, "endCursor": None}
        custom = self.base / "capped.json"
        custom.write_text(json.dumps(page))
        self.gh_rules([{"match": ["BulkIssueSearch"], "file": str(custom)}])
        result, out = self.select("--limit", "100", "--scan", "1000")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual((summary["ceiling_reached"], summary["exhausted"]), (True, False))

    def test_partial_graphql_response_is_an_error(self):
        page = json.loads((FIXTURES / "page1.json").read_text())
        for data in (page["data"], None):
            with self.subTest(data=data is not None):
                custom = self.base / "partial.json"
                custom.write_text(json.dumps({"data": data, "errors": [{"message": "API rate limit exceeded"}]}))
                self.gh_rules([{"match": ["BulkIssueSearch"], "file": str(custom)}])
                result, out = self.select("--limit", "10", "--scan", "100")
                self.assertEqual(result.returncode, 1)
                self.assertIn("Error: ", result.stderr)
                self.assertFalse(out.exists())

    def select(self, *extra, out=None):
        out = out or self.base / "selection.json"
        result = self.bulk("select", "--repo", REPO, "--out", out, *extra)
        return result, out

    def test_limit_pages_past_skipped_candidates(self):
        self.gh_rules(search_rules())
        result, out = self.select("--limit", "10", "--scan", "100", "--search", "label:bug crash")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        selection = json.loads(out.read_text())
        self.assertEqual(len(self.gh_calls()), 2)
        self.assertEqual(summary, {"scanned": 21, "selected": 10, "skipped": 11,
                                   "ceiling_reached": False, "exhausted": False})
        self.assertEqual([c["number"] for c in selection["selected"]],
                         [137, 136, 135, 132, 130, 129, 128, 127, 125, 120])
        self.assertEqual(len(selection["selected"]) + len(selection["skipped"]), selection["scanned"])
        stamps = [c["created_at"] for c in selection["selected"]]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        self.assertEqual(selection["query"], "repo:acme/widgets is:issue is:open sort:created-desc label:bug crash")
        sent = self.gh_calls()[0]["args"]
        self.assertIn("q=repo:acme/widgets is:issue is:open sort:created-desc label:bug crash", sent)
        self.assertEqual(sent[:4], ["api", "--hostname", "github.com", "graphql"])
        reasons = {s["number"]: (s["reason"], s["pr"]) for s in selection["skipped"]}
        self.assertEqual(reasons[134], ("maintainer_pr", 501))
        self.assertEqual(reasons[138], ("maintainer_replied", None))
        self.assertEqual(reasons[139], ("already_assessed", None))
        self.assertEqual(reasons[126], ("history_too_long", None))
        linked = {c["number"]: c["linked_prs"] for c in selection["selected"]}
        self.assertTrue(linked[130][0]["open_non_maintainer"])
        self.assertEqual(selection["repository"], REPO)

    def test_without_search_uses_fixed_qualifiers_only(self):
        self.gh_rules(search_rules())
        result, out = self.select("--limit", "1", "--scan", "100")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(out.read_text())["query"], "repo:acme/widgets is:issue is:open sort:created-desc")
        self.assertEqual(len(self.gh_calls()), 1)

    def test_scan_ceiling_stops_early(self):
        self.gh_rules(search_rules())
        result, out = self.select("--limit", "10", "--scan", "15")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary, {"scanned": 15, "selected": 8, "skipped": 7,
                                   "ceiling_reached": True, "exhausted": False})
        self.assertEqual(len(self.gh_calls()), 1)

    def test_exhausted_after_last_page_and_dedupe(self):
        self.gh_rules(search_rules())
        result, out = self.select("--limit", "50", "--scan", "100")
        self.assertEqual(result.returncode, 0, result.stderr)
        selection = json.loads(out.read_text())
        self.assertEqual((selection["scanned"], selection["exhausted"], selection["ceiling_reached"]),
                         (31, True, False))
        numbers = [c["number"] for c in selection["selected"]] + [s["number"] for s in selection["skipped"]]
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertEqual(numbers.count(125), 1)
        self.assertEqual(len(selection["selected"]), 18)
        self.assertEqual(len(selection["selected"]) + len(selection["skipped"]), selection["scanned"])

    def test_closed_foreign_and_pull_request_nodes_are_not_candidates(self):
        page = json.loads((FIXTURES / "page2.json").read_text())
        nodes = page["data"]["search"]["nodes"]
        closed = dict(nodes[1], number=99, url="https://github.com/acme/widgets/issues/99", state="CLOSED")
        foreign = dict(nodes[2], number=98, url="https://github.com/other/repo/issues/98")
        pull = {"__typename": "PullRequest", "number": 97, "url": "https://github.com/acme/widgets/pull/97"}
        twice = nodes[3]
        page["data"]["search"]["nodes"] = [closed, foreign, pull, twice, twice] + nodes[4:6]
        custom = self.base / "custom-page.json"
        custom.write_text(json.dumps(page))
        self.gh_rules([{"match": ["BulkIssueSearch"], "file": str(custom)}])
        result, out = self.select("--limit", "10", "--scan", "100")
        self.assertEqual(result.returncode, 0, result.stderr)
        selection = json.loads(out.read_text())
        numbers = [c["number"] for c in selection["selected"]] + [s["number"] for s in selection["skipped"]]
        self.assertEqual(sorted(numbers), sorted([twice["number"], nodes[4]["number"], nodes[5]["number"]]))
        self.assertEqual(selection["scanned"], 3)
        self.assertTrue(selection["exhausted"])

    def test_missing_cursor_is_an_error_not_an_empty_queue(self):
        page = json.loads((FIXTURES / "page1.json").read_text())
        page["data"]["search"]["pageInfo"] = {"hasNextPage": True, "endCursor": None}
        custom = self.base / "no-cursor.json"
        custom.write_text(json.dumps(page))
        self.gh_rules([{"match": ["BulkIssueSearch"], "file": str(custom)}])
        result, out = self.select("--limit", "10", "--scan", "100")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: ", result.stderr)
        self.assertFalse(out.exists())

    def test_failure_on_later_page_writes_nothing(self):
        self.gh_rules(search_rules(fail_page2=True))
        result, out = self.select("--limit", "10", "--scan", "100")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("Error: "), result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(out.exists())
        self.assertEqual(sorted(p.name for p in out.parent.iterdir() if p.name.startswith("selection")), [])


class ValidateTests(BulkTestCase):
    def ok(self, *args):
        result = self.bulk("validate", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.gh_calls(), [])
        return json.loads(result.stdout)

    def rejected(self, *args, message=None):
        result = self.bulk("validate", *args)
        self.assertEqual(result.returncode, 2, (args, result.stdout, result.stderr))
        self.assertTrue(result.stderr.startswith("Error: "), result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.gh_calls(), [])
        if message:
            self.assertIn(message, result.stderr)
        return result.stderr

    def test_defaults(self):
        self.assertEqual(self.ok("--bulk"), {"mode": "new", "search": None, "limit": 10, "scan": 100,
                                             "repo": None, "resume_id": None})

    def test_full_new_run(self):
        self.assertEqual(self.ok("--bulk", "--search", "label:bug crash", "--limit", "5", "--scan", "30",
                                 "--repo", REPO),
                         {"mode": "new", "search": "label:bug crash", "limit": 5, "scan": 30,
                          "repo": REPO, "resume_id": None})
        self.assertEqual(self.ok("--search=label:docs", "--bulk", "--limit=100", "--scan=1000")["limit"], 100)
        self.assertEqual(self.ok("--bulk", "--limit", "1", "--scan", "1")["scan"], 1)
        self.assertEqual(self.ok("--bulk", "--search", "type:bug label:\"good first issue\"")["search"],
                         "type:bug label:\"good first issue\"")

    def test_resume_modes(self):
        self.assertEqual(self.ok("--resume"), {"mode": "resume", "search": None, "limit": None, "scan": None,
                                               "repo": None, "resume_id": None})
        self.assertEqual(self.ok("--resume", "20261123-091446-issue")["resume_id"], "20261123-091446-issue")
        self.assertEqual(self.ok("--bulk", "--resume", "20261123-091446-issue-2")["mode"], "resume")
        self.rejected("--resume", "../etc", message="run id")

    def test_issue_target_with_bulk_or_resume(self):
        for args in (("--bulk", "42"), ("42", "--bulk"), ("--resume", "42"),
                     ("--bulk", "https://github.com/acme/widgets/issues/4"),
                     ("--resume", "--bulk", "7")):
            with self.subTest(args=args):
                self.rejected(*args, message="a bulk run selects its own issues")

    def test_unattended_is_rejected(self):
        for args in (("--bulk", "--unattended"), ("--unattended", "--resume"),
                     ("--resume", "20261123-091446-issue", "--unattended")):
            with self.subTest(args=args):
                self.rejected(*args, message="interactive only")

    def test_bulk_only_flags_without_bulk(self):
        for flag, value in (("--search", "label:bug"), ("--limit", "5"), ("--scan", "50")):
            with self.subTest(flag=flag):
                error = self.rejected(flag, value)
                self.assertIn(flag, error)
                self.assertIn("--bulk", error)

    def test_resume_keeps_recorded_options(self):
        for args in (("--search", "label:bug"), ("--limit", "5"), ("--scan", "50"), ("--repo", REPO)):
            for resume in (("--resume",), ("--bulk", "--resume"), ("--resume", "20261123-091446-issue")):
                with self.subTest(args=args, resume=resume):
                    self.rejected(*resume, *args, message="a resumed run keeps its recorded options")

    def test_ranges(self):
        for args in (("--limit", "0"), ("--limit", "101"), ("--limit", "abc"), ("--limit", "-1"),
                     ("--scan", "0"), ("--scan", "1001"), ("--limit", "20", "--scan", "10"),
                     ("--limit",), ("--scan", "")):
            with self.subTest(args=args):
                self.rejected("--bulk", *args)
        self.assertIn("1 to 100", self.rejected("--bulk", "--limit", "101"))
        self.assertIn("1 to 1000", self.rejected("--bulk", "--scan", "1001"))
        self.assertIn("below --limit", self.rejected("--bulk", "--limit", "20", "--scan", "10"))

    def test_search_qualifiers_are_fixed(self):
        for search in ("repo:other/repo", "org:acme", "user:someone", "is:pr", "type:pr", "is:closed",
                       "is:merged", "is:open", "state:open", "is:issue", "sort:updated-desc",
                       "-is:open", "label:bug -repo:acme/widgets", "IS:OPEN", "Sort:created-asc",
                       "\"is:closed\"", "label:bug 'org:acme'", "(is:pr)", "crash   -state:closed",
                       "is:\"closed\"", "type:'pr'", "label:x is:\"open\""):
            with self.subTest(search=search):
                self.rejected("--bulk", "--search", search, message="--search")

    def test_other_invalid_input(self):
        for args in ((), ("--bulk", "--post"), ("--bulk", "--repo", "bad"), ("--bulk", "--repo", "a/.."),
                     ("--bulk", "--search"), ("--bulk", "--search", "")):
            with self.subTest(args=args):
                self.rejected(*args)


OPEN_PR = {"number": 505, "url": "https://github.com/acme/widgets/pull/505", "state": "OPEN", "merged": False,
           "author": "newcomer", "maintainer_owned": False, "open_non_maintainer": True}
CLOSED_PR = {"number": 506, "url": "https://github.com/acme/widgets/pull/506", "state": "CLOSED", "merged": False,
             "author": "newcomer", "maintainer_owned": True, "open_non_maintainer": False}
REPO_VIEW = {"match": ["repo", "view", "viewerPermission"],
             "stdout": {"nameWithOwner": REPO, "url": "https://github.com/acme/widgets",
                        "defaultBranchRef": {"name": "main"}, "viewerPermission": "WRITE"}}
USER = {"match": ["api", "user"], "absent": ["graphql"], "stdout": {"login": "maint"}}


def candidate(number, linked=()):
    return {"number": number, "url": "https://github.com/acme/widgets/issues/%d" % number,
            "title": "Issue %d" % number, "author": "reporter",
            "created_at": "2026-11-%02dT10:00:00Z" % (number % 28 + 1), "linked_prs": [dict(p) for p in linked]}


def make_selection(selected, skipped=(), query="repo:acme/widgets is:issue is:open sort:created-desc"):
    return {"repository": REPO, "query": query,
            "options": {"search": None, "limit": 10, "scan": 100, "repo": REPO},
            "scanned": len(selected) + len(skipped), "ceiling_reached": False, "exhausted": True,
            "selected": list(selected), "skipped": list(skipped)}


class StartTests(BulkTestCase):
    def write_selection(self, selection):
        path = self.base / "selection.json"
        path.write_text(json.dumps(selection))
        return path

    def test_start_in_matching_checkout_with_push_permission(self):
        work, _ = self.make_repo(origin_url="https://github.com/acme/widgets.git")
        sel = self.write_selection(make_selection([candidate(12, [OPEN_PR]), candidate(11)]))
        self.gh_rules([REPO_VIEW, USER])
        out = self.bulk_ok("start", "--selection", sel, cwd=work)
        self.assertEqual((out["selected"], out["fixes_available"], out["fixes_unavailable_reason"]), (2, True, None))
        self.assertRegex(out["run_id"], r"^[0-9]{8}-[0-9]{6}-issue(-[0-9]+)?$")
        # Run state never lives in the checkout, even when it is the verified clone that enables fixes.
        self.assertEqual(out["run_dir"], str(self.state_home / "cc-review/issue-bulk/acme__widgets" / out["run_id"]))
        state = json.loads((Path(out["run_dir"]) / "state.json").read_text())
        self.assertEqual((state["kind"], state["repository"], state["user"], state["status"]),
                         ("issue", REPO, "maint", "running"))
        self.assertEqual(state["extra"]["default_branch"], "main")
        self.assertEqual(state["extra"]["checkout_root"], str(work))
        self.assertEqual(state["extra"]["order"], [12, 11])
        self.assertEqual(state["options"]["limit"], 10)
        item = state["items"]["12"]
        self.assertEqual((item["phase"], item["post"]), ("selected", {"comment": "pending", "comment_url": None,
                                                                    "label": "pending", "reason": None}))
        self.assertEqual(item["linked_prs"], [OPEN_PR])
        self.assertEqual(json.loads((Path(out["run_dir"]) / "selection.json").read_text())["scanned"], 2)
        self.assertEqual(git(work, "status", "--porcelain", "--untracked-files=all"), "")

    def test_without_push_permission_fixes_are_unavailable(self):
        work, _ = self.make_repo(origin_url="https://github.com/acme/widgets.git")
        sel = self.write_selection(make_selection([candidate(12)]))
        view = json.loads(json.dumps(REPO_VIEW))
        view["stdout"]["viewerPermission"] = "READ"
        self.gh_rules([view, USER])
        out = self.bulk_ok("start", "--selection", sel, cwd=work)
        self.assertFalse(out["fixes_available"])
        self.assertIn("push", out["fixes_unavailable_reason"])

    def test_without_matching_checkout_state_is_per_user(self):
        sel = self.write_selection(make_selection([candidate(12)]))
        self.gh_rules([REPO_VIEW, USER])
        out = self.bulk_ok("start", "--selection", sel, cwd=self.base)
        self.assertFalse(out["fixes_available"])
        self.assertIn("checkout", out["fixes_unavailable_reason"])
        self.assertTrue(out["run_dir"].startswith(str(self.state_home / "cc-review/issue-bulk/acme__widgets")))
        state = json.loads((Path(out["run_dir"]) / "state.json").read_text())
        self.assertIsNone(state["extra"]["checkout_root"])

    def test_empty_selection_is_refused(self):
        sel = self.write_selection(make_selection([], skipped=[{"number": 3, "url": "u", "title": "t",
                                                                "reason": "maintainer_replied", "pr": None}]))
        self.gh_rules([REPO_VIEW, USER])
        result = self.bulk("start", "--selection", sel)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: ", result.stderr)
        self.assertEqual(self.gh_calls(), [])
        self.assertFalse(self.state_home.exists())

    def test_resolve_repo(self):
        self.gh_rules([{"match": ["repo", "view", "github.com/acme/widgets"],
                        "stdout": {"nameWithOwner": REPO, "url": "https://github.com/acme/widgets"}},
                       {"match": ["repo", "view"], "absent": ["github.com/"],
                        "stdout": {"nameWithOwner": "Acme/Gadgets", "url": "https://github.com/Acme/Gadgets"}}])
        self.assertEqual(self.bulk_ok("resolve-repo", "--repo", REPO), {"repository": REPO})
        self.assertEqual(self.bulk_ok("resolve-repo"), {"repository": "Acme/Gadgets"})
        self.gh_rules([{"match": ["repo", "view"], "stdout": {"nameWithOwner": "other/x",
                                                               "url": "https://github.com/other/x"}}])
        self.assertEqual(self.bulk("resolve-repo", "--repo", REPO).returncode, 1)


def assess_issue_node(number, state="OPEN"):
    url = "https://github.com/acme/widgets/issues/%d" % number
    return {"__typename": "Issue", "number": number, "title": "Issue %d" % number, "url": url,
            "body": "Steps: run widgets --fast. Expected output, got a crash.", "state": state,
            "author": {"login": "reporter"}, "createdAt": "2026-11-01T10:00:00Z",
            "updatedAt": "2026-11-01T10:00:00Z",
            "comments": {"totalCount": 0, "pageInfo": {"hasPreviousPage": False}, "nodes": []}}


def collect_rules(number):
    return [{"match": ["repo", "view", "nameWithOwner,url"], "absent": ["viewerPermission"],
             "stdout": {"nameWithOwner": REPO, "url": "https://github.com/acme/widgets"}},
            {"match": ["AssessIssue", "number=%d" % number],
             "stdout": {"data": {"repository": {"issueOrPullRequest": assess_issue_node(number)}}}}]


class RunTestCase(BulkTestCase):
    """Creates runs directly with run_state, as start would, without gh."""

    def new_run(self, candidates, root=None, **extra):
        bulk = load("issue_bulk")
        rs = load("run_state")
        settings = {"fixes_available": True, "fixes_unavailable_reason": None, "default_branch": "main",
                    "checkout_root": None, "handoff_prs": [], "order": [c["number"] for c in candidates]}
        settings.update(extra)
        items = {str(c["number"]): bulk.new_item(c) for c in candidates}
        run_dir = rs.init(str(root or self.base / "runs"), "issue", REPO, "maint",
                          {"search": None, "limit": 10, "scan": 100, "repo": REPO}, settings, items)
        (Path(run_dir) / "selection.json").write_text(json.dumps(make_selection(candidates)))
        return Path(run_dir)

    def state(self, run_dir):
        return json.loads((Path(run_dir) / "state.json").read_text())

    def item(self, run_dir, number):
        return self.state(run_dir)["items"][str(number)]

    def set_item(self, run_dir, number, **fields):
        load("run_state").set_item(str(run_dir), number, **fields)


class CollectTests(RunTestCase):
    def test_collect_writes_snapshot_with_linked_prs(self):
        run = self.new_run([candidate(12, [OPEN_PR])])
        self.gh_rules(collect_rules(12))
        out = self.bulk_ok("collect", run, "12")
        self.assertEqual(out, {"number": 12, "ok": True, "warnings": 0})
        snapshot = json.loads((run / "items/12/snapshot.json").read_text())
        self.assertEqual(snapshot["issue"]["number"], 12)
        self.assertEqual(snapshot["linked_prs"], [OPEN_PR])
        self.assertEqual(self.item(run, 12)["phase"], "collected")

    def test_collect_failure_marks_assessment_failed(self):
        run = self.new_run([candidate(12)])
        self.gh_rules([collect_rules(12)[0], {"match": ["AssessIssue"], "stderr": "HTTP 502", "exit": 1}])
        out = self.bulk_ok("collect", run, "12")
        self.assertEqual((out["number"], out["ok"]), (12, False))
        item = self.item(run, 12)
        self.assertEqual(item["phase"], "assessment_failed")
        self.assertIn("502", item["failure"])
        self.assertFalse((run / "items/12/snapshot.json").exists())

    def test_collect_unknown_item_is_an_error(self):
        run = self.new_run([candidate(12)])
        result = self.bulk("collect", run, "13")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: ", result.stderr)


BUG = {"kind": "bug", "use_case": "Users run widgets --fast in CI.", "why": "The crash blocks their pipeline.",
       "concrete_example": True, "check": {"result": "confirmed", "note": "src/app.py:12 divides by zero."},
       "severity": "medium", "severity_reason": "It blocks one flag.", "alternatives": ["Run without --fast."],
       "fit": "Yes, the README documents --fast.", "recommendation": "pursue",
       "recommendation_reason": "A small, confirmed defect.", "limits": "",
       "summary": "A confirmed crash with a small fix."}
NEEDS_EVIDENCE = dict(BUG, concrete_example=False, check={"result": "unverified", "note": "Not reproduced."},
                      severity=None, severity_reason="", alternatives=[], recommendation="needs_evidence",
                      recommendation_reason="We need the exact steps.")
ESTIMATE = {"confirmed": True, "files": 1, "lines": 10, "test_lines": 20, "note": "Guard the division in src/app.py."}


def assessment_file(run_dir, number, body="Thanks for the clear steps. We can reproduce this.",
                    assessment=None, estimate=None, **changes):
    data = {"body": body, "assessment": dict(assessment or BUG), "fix_estimate": dict(estimate or ESTIMATE)}
    data.update(changes)
    path = Path(run_dir) / "items" / str(number) / "assessment.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


class RenderItemTests(RunTestCase):
    def collected_run(self, candidates=None, **extra):
        run = self.new_run(candidates or [candidate(12)], **extra)
        for c in candidates or [candidate(12)]:
            self.set_item(run, c["number"], phase="collected")
        return run

    def test_render_valid_assessment(self):
        run = self.collected_run()
        assessment_file(run, 12, body="Thanks \u2014 we can reproduce this.")
        out = self.bulk_ok("render-item", run, "12")
        self.assertEqual(out, {"number": 12, "recommendation": "pursue", "label": "cc-review:pursue",
                               "fix_eligible": True, "fix_ineligible_reason": None, "linked_open_prs": []})
        rendered = (run / "items/12/rendered.md").read_text()
        run_id = run.name
        self.assertTrue(rendered.endswith("<!-- cc-review:issue-bulk run=%s -->\n" % run_id))
        self.assertIn("<!-- cc-review:assessment {", rendered)
        self.assertNotIn("\u2014", rendered)
        item = self.item(run, 12)
        self.assertEqual(item["rendered_sha256"], hashlib.sha256(rendered.encode()).hexdigest())
        self.assertEqual((item["phase"], item["kind"], item["label"]), ("assessed", "bug", "cc-review:pursue"))

    def test_fix_bound_boundaries(self):
        cases = [({"files": 3, "lines": 100, "test_lines": 300}, True),
                 ({"files": 4}, False), ({"lines": 101}, False), ({"test_lines": 301}, False),
                 ({"confirmed": False}, False)]
        for change, eligible in cases:
            with self.subTest(change=change):
                run = self.collected_run()
                assessment_file(run, 12, estimate=dict(ESTIMATE, **change))
                out = self.bulk_ok("render-item", run, "12")
                self.assertEqual(out["fix_eligible"], eligible)
                if not eligible:
                    self.assertTrue(out["fix_ineligible_reason"])
        run = self.collected_run()
        assessment_file(run, 12, estimate=dict(ESTIMATE, files=4))
        self.assertIn("small bound", self.bulk_ok("render-item", run, "12")["fix_ineligible_reason"])

    def test_not_pursue_or_fixes_unavailable(self):
        run = self.collected_run()
        assessment_file(run, 12, assessment=NEEDS_EVIDENCE, estimate=dict(ESTIMATE, confirmed=False))
        out = self.bulk_ok("render-item", run, "12")
        self.assertEqual((out["fix_eligible"], out["label"]), (False, "cc-review:needs-evidence"))
        self.assertIn("Pursue", out["fix_ineligible_reason"])
        run = self.collected_run(fixes_available=False, fixes_unavailable_reason="No verified local checkout.")
        assessment_file(run, 12)
        out = self.bulk_ok("render-item", run, "12")
        self.assertFalse(out["fix_eligible"])
        self.assertIn("No verified local checkout", out["fix_ineligible_reason"])

    def test_open_linked_pr_must_be_named_and_blocks_fix(self):
        run = self.collected_run([candidate(12, [OPEN_PR, CLOSED_PR])])
        assessment_file(run, 12)
        result = self.bulk("render-item", run, "12")
        self.assertEqual(result.returncode, 1)
        self.assertIn(OPEN_PR["url"], result.stderr)
        self.assertEqual(self.item(run, 12)["phase"], "collected")
        assessment_file(run, 12, body="Thanks! There is already a pull request: " + OPEN_PR["url"])
        out = self.bulk_ok("render-item", run, "12")
        self.assertEqual((out["fix_eligible"], out["linked_open_prs"]), (False, [505]))
        self.assertIn("linked PR under review", out["fix_ineligible_reason"])

    def test_invalid_input_names_the_field_and_keeps_phase(self):
        bad_bug = dict(BUG, check={"result": "unverified", "note": "Not read."}, severity=None,
                       severity_reason="", alternatives=[], concrete_example=True)
        cases = [({"fix_estimate": None}, "fix_estimate"),
                 ({"fix_estimate": dict(ESTIMATE, files=-1)}, "fix_estimate.files"),
                 ({"fix_estimate": dict(ESTIMATE, lines="10")}, "fix_estimate.lines"),
                 ({"fix_estimate": {"confirmed": True, "files": 1, "lines": 1}}, "fix_estimate"),
                 ({"assessment": dict(BUG, kind="wish")}, "assessment.kind"),
                 ({"assessment": bad_bug}, "check.result"),
                 ({"body": 7}, "body")]
        for change, field in cases:
            with self.subTest(field=field):
                run = self.collected_run()
                path = assessment_file(run, 12)
                data = json.loads(path.read_text())
                data.update(change)
                if data.get("fix_estimate") is None:
                    data.pop("fix_estimate")
                path.write_text(json.dumps(data))
                result = self.bulk("render-item", run, "12")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(field, result.stderr)
                self.assertEqual(self.item(run, 12)["phase"], "collected")
                self.assertFalse((run / "items/12/rendered.md").exists())
        run = self.collected_run()
        self.assertEqual(self.bulk("render-item", run, "12").returncode, 1)

    def test_edit_recomputes_label_eligibility_and_clears_decision(self):
        run = self.collected_run()
        assessment_file(run, 12)
        first = self.bulk_ok("render-item", run, "12")
        self.assertTrue(first["fix_eligible"])
        self.set_item(run, 12, decision={"post": "post", "action": "fix", "rendered_sha256": "x"})
        assessment_file(run, 12, assessment=NEEDS_EVIDENCE, estimate=dict(ESTIMATE, confirmed=False),
                        body="Could you share the exact steps?")
        second = self.bulk_ok("render-item", run, "12")
        self.assertEqual((second["recommendation"], second["label"], second["fix_eligible"]),
                         ("needs_evidence", "cc-review:needs-evidence", False))
        item = self.item(run, 12)
        self.assertIsNone(item["decision"])
        self.assertEqual(item["phase"], "assessed")
        self.assertIn("Could you share", (run / "items/12/rendered.md").read_text())

    def test_project_label_mapping_is_used(self):
        work, _ = self.make_repo()
        (work / ".cc-review").mkdir()
        (work / ".cc-review/ci.yml").write_text(json.dumps({"labels": {"pursue": "triage:go"}}))
        run = self.collected_run(checkout_root=str(work))
        assessment_file(run, 12)
        self.assertEqual(self.bulk_ok("render-item", run, "12")["label"], "triage:go")
        assessment_file(run, 12, assessment=NEEDS_EVIDENCE, estimate=dict(ESTIMATE, confirmed=False))
        self.assertEqual(self.bulk_ok("render-item", run, "12")["label"], "cc-review:needs-evidence")

    def test_posted_item_is_not_rendered_again(self):
        run = self.collected_run()
        assessment_file(run, 12)
        self.set_item(run, 12, phase="posted")
        self.assertEqual(self.bulk("render-item", run, "12").returncode, 1)


class NextDecideTests(RunTestCase):
    def assessed_run(self, candidates, eligible=True):
        run = self.new_run(candidates)
        for c in candidates:
            self.set_item(run, c["number"], phase="collected")
            assessment_file(run, c["number"], body="Thanks! See " + " ".join(p["url"] for p in c["linked_prs"]),
                            estimate=dict(ESTIMATE, files=1 if eligible else 9))
            self.bulk_ok("render-item", run, str(c["number"]))
        return run

    def next(self, run, phase, *extra):
        return self.bulk_ok("next", run, phase, *extra)["number"]

    def test_next_follows_selection_order_per_phase(self):
        run = self.new_run([candidate(12), candidate(30), candidate(11)])
        self.assertEqual(self.next(run, "collect"), 12)
        self.set_item(run, 12, phase="collected")
        self.assertEqual(self.next(run, "collect"), 30)
        self.assertEqual(self.next(run, "assess"), 12)
        self.set_item(run, 30, phase="assessment_failed", failure="x")
        self.set_item(run, 11, phase="assessed")
        self.assertEqual(self.next(run, "collect"), None)
        self.assertEqual(self.next(run, "assess"), 12)
        self.set_item(run, 12, phase="assessed")
        # 11 is assessed without rendered.md, so it still needs assessing.
        self.assertEqual(self.next(run, "assess"), 12)
        (run / "items/12").mkdir(parents=True)
        (run / "items/12/rendered.md").write_text("x")
        self.assertEqual(self.next(run, "assess"), 11)
        self.assertEqual(self.next(run, "decide"), 12)
        self.assertEqual(self.bulk("next", run, "bogus").returncode, 2)

    def test_next_post_and_fix_skip_items_tried_in_this_session(self):
        run = self.new_run([candidate(12), candidate(11)])
        decided = {"post": "post", "action": "fix", "rendered_sha256": "x"}
        for n in (12, 11):
            self.set_item(run, n, phase="decided", decision=decided)
        self.assertEqual(self.next(run, "post"), 12)
        self.set_item(run, 12, attempt_session={"post": "S1"})
        self.assertEqual(self.next(run, "post", "--session", "S1"), 11)
        self.assertEqual(self.next(run, "post", "--session", "S2"), 12)
        self.set_item(run, 12, post={"comment": "posted", "comment_url": "u", "label": "failed", "reason": "r"})
        self.assertEqual(self.next(run, "post", "--session", "S2"), 12)
        self.set_item(run, 12, post={"comment": "posted", "comment_url": "u", "label": "applied", "reason": None})
        self.set_item(run, 11, post={"comment": "withheld", "comment_url": None, "label": "none", "reason": "r"})
        self.assertEqual(self.next(run, "post"), None)
        self.assertEqual(self.next(run, "fix"), 12)
        self.set_item(run, 12, attempt_session={"post": "S1", "fix": "S1"})
        self.assertEqual(self.next(run, "fix", "--session", "S1"), 11)
        self.set_item(run, 11, fix={"abandoned": "worker gave up", "pr_url": None,
                                    "steps": {"prepared": True}, "cleaned": False})
        self.assertEqual(self.next(run, "fix", "--session", "S1"), 11)
        self.set_item(run, 11, fix={"abandoned": "worker gave up", "pr_url": None,
                                    "steps": {"prepared": True}, "cleaned": True})
        self.set_item(run, 12, fix={"abandoned": None, "pr_url": None, "pending": "pr"})
        self.assertEqual(self.next(run, "fix", "--session", "S1"), None)
        self.assertEqual(self.next(run, "fix", "--session", "S2"), 12)
        self.set_item(run, 12, fix={"abandoned": None, "pr_url": "https://github.com/acme/widgets/pull/9"})
        self.assertEqual(self.next(run, "fix"), None)

    def test_fail_marks_assessment_failed(self):
        run = self.new_run([candidate(12)])
        self.set_item(run, 12, phase="collected")
        self.assertEqual(self.bulk_ok("fail", run, "12", "--reason", "worker wrote no assessment.json"),
                         {"number": 12, "phase": "assessment_failed"})
        item = self.item(run, 12)
        self.assertEqual((item["phase"], item["failure"]), ("assessment_failed", "worker wrote no assessment.json"))
        self.assertIsNone(self.next(run, "assess"))
        self.assertIsNone(self.next(run, "decide"))

    def test_decide_records_hash_and_phase(self):
        run = self.assessed_run([candidate(12), candidate(11), candidate(10)])
        sha = self.item(run, 12)["rendered_sha256"]
        out = self.bulk_ok("decide", run, "12", "--post", "post", "--action", "fix")
        self.assertEqual(out["decision"], {"post": "post", "action": "fix", "rendered_sha256": sha})
        self.assertEqual(self.item(run, 12)["phase"], "decided")
        self.bulk_ok("decide", run, "11", "--post", "skip")
        item = self.item(run, 11)
        self.assertEqual((item["phase"], item["post"]["comment"], item["post"]["label"]), ("done", "skipped", "none"))
        self.assertEqual(item["decision"]["action"], None)
        self.bulk_ok("decide", run, "10", "--post", "skip", "--action", "fix")
        item = self.item(run, 10)
        self.assertEqual((item["phase"], item["post"]["comment"]), ("decided", "skipped"))
        self.assertEqual(self.next(run, "post"), 12)
        self.assertEqual(self.next(run, "fix"), 12)
        self.set_item(run, 12, fix={"abandoned": "x", "pr_url": None})
        self.assertEqual(self.next(run, "fix"), 10)
        self.assertEqual(self.bulk("decide", run, "12", "--post", "post").returncode, 1)

    def test_decide_skip_with_leave_or_review_is_done(self):
        run = self.assessed_run([candidate(12, [OPEN_PR]), candidate(11)])
        self.bulk_ok("decide", run, "12", "--post", "skip", "--action", "review")
        self.assertEqual(self.item(run, 12)["phase"], "done")
        self.bulk_ok("decide", run, "11", "--post", "skip", "--action", "leave")
        self.assertEqual(self.item(run, 11)["phase"], "done")

    def test_decide_rejects_unavailable_actions(self):
        run = self.assessed_run([candidate(12)], eligible=False)
        result = self.bulk("decide", run, "12", "--post", "post", "--action", "fix")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not fix-eligible", result.stderr)
        result = self.bulk("decide", run, "12", "--post", "post", "--action", "review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("open", result.stderr)
        self.assertEqual(self.item(run, 12)["phase"], "assessed")
        self.assertEqual(self.bulk("decide", run, "12", "--post", "maybe").returncode, 2)
        run = self.assessed_run([candidate(12, [OPEN_PR])])
        self.bulk_ok("decide", run, "12", "--post", "post", "--action", "review")

    def test_decide_refuses_changed_rendering(self):
        run = self.assessed_run([candidate(12)])
        (run / "items/12/rendered.md").write_text("tampered\n")
        result = self.bulk("decide", run, "12", "--post", "post")
        self.assertEqual(result.returncode, 1)
        self.assertIn("render-item", result.stderr)


def recheck_node(number, state="OPEN", comments=(), timeline=()):
    return {"__typename": "Issue", "number": number, "title": "Issue %d" % number, "state": state,
            "url": "https://github.com/acme/widgets/issues/%d" % number, "createdAt": "2026-11-01T10:00:00Z",
            "author": {"login": "reporter", "__typename": "User"}, "authorAssociation": "NONE",
            "comments": {"totalCount": len(comments), "pageInfo": {"hasPreviousPage": False},
                         "nodes": list(comments)},
            "timelineItems": {"totalCount": len(timeline), "pageInfo": {"hasPreviousPage": False},
                              "nodes": list(timeline)}}


def gh_comment(login, body, association="NONE", number=12, cid=1, typename="User"):
    return {"url": "https://github.com/acme/widgets/issues/%d#issuecomment-%d" % (number, cid), "body": body,
            "authorAssociation": association, "author": {"login": login, "__typename": typename}}


def recheck_rule(node):
    return {"match": ["BulkIssueRecheck"], "stdout": {"data": {"repository": {"issue": node}}}}


COMMENT_OK = {"match": ["repos/acme/widgets/issues/12/comments", "POST"],
              "stdout": {"id": 77, "html_url": "https://github.com/acme/widgets/issues/12#issuecomment-77"}}
LABEL_EXISTS = {"match": ["repos/acme/widgets/labels/cc-review%3Apursue"], "stdout": {"name": "cc-review:pursue"}}
LABEL_ADD = {"match": ["repos/acme/widgets/issues/12/labels", "POST"], "stdout": [{"name": "cc-review:pursue"}]}


class ItemGuardLockTests(RunTestCase):
    def test_item_prints_one_items_decision_fields(self):
        run = self.new_run([candidate(12, [OPEN_PR]), candidate(11)])
        out = self.bulk_ok("item", run, "12")
        self.assertEqual(set(out), {"number", "title", "url", "phase", "recommendation", "label", "fix_eligible",
                                    "fix_ineligible_reason", "linked_prs", "decision", "post", "failure"})
        self.assertEqual((out["number"], out["phase"], out["linked_prs"][0]["number"]), (12, "selected", 505))
        self.assertEqual(self.bulk("item", run, "99").returncode, 1)

    def test_guard_passes_when_the_worker_writes_only_its_assessment(self):
        run = self.new_run([candidate(12), candidate(11)])
        self.set_item(run, 12, phase="collected")
        (run / "items/11").mkdir(parents=True)
        (run / "items/11/snapshot.json").write_text("{}")
        digest = self.bulk_ok("guard-begin", run, "12", "--session", "S1")["digest"]
        assessment_file(run, 12)
        self.assertEqual(self.bulk_ok("guard-end", run, "12", "--digest", digest, "--session", "S1"),
                         {"number": 12, "unchanged": True})
        self.assertEqual(self.bulk_ok("render-item", run, "12")["number"], 12)

    def test_guard_stops_the_run_when_a_worker_writes_elsewhere(self):
        tampering = [lambda run: load("run_state").set_item(str(run), 11, decision={"post": "skip", "action": "fix"}),
                     lambda run: (run / "items/11/snapshot.json").write_text('{"body": "forged"}'),
                     lambda run: (run / "selection.json").write_text("{}")]
        for tamper in tampering:
            with self.subTest(tamper=tamper):
                run = self.new_run([candidate(12), candidate(11)])
                self.set_item(run, 12, phase="collected")
                (run / "items/11").mkdir(parents=True)
                (run / "items/11/snapshot.json").write_text("{}")
                digest = self.bulk_ok("guard-begin", run, "12")["digest"]
                assessment_file(run, 12)
                tamper(run)
                result = self.bulk("guard-end", run, "12", "--digest", digest)
                self.assertEqual(result.returncode, 1)
                self.assertIn("assessment worker for #12", result.stderr)
                # The run is stopped: no further work, but it can be inspected and abandoned.
                self.assertEqual(self.bulk("next", run, "assess").returncode, 1)
                self.assertEqual(self.bulk("render-item", run, "12").returncode, 1)
                self.assertEqual(self.bulk("item", run, "12").returncode, 0)
                self.assertEqual(self.bulk("report", run).returncode, 0)
                self.assertEqual(self.bulk_ok("abandon-run", run)["status"], "abandoned")

    def test_second_session_is_refused_until_the_lock_expires(self):
        self.expire_session_locks = False
        run = self.new_run([candidate(12)])
        self.assertEqual(self.bulk_ok("next", run, "collect", "--session", "A")["number"], 12)
        refused = self.bulk("next", run, "collect", "--session", "B")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("in use by another session", refused.stderr)
        self.assertEqual(self.bulk_ok("next", run, "collect", "--session", "A")["number"], 12)
        lock = run / "lock"
        lock.write_text(json.dumps({"session": "A", "updated_at": "2000-01-01T00:00:00Z"}))
        self.assertEqual(self.bulk_ok("next", run, "collect", "--session", "B")["number"], 12)
        self.assertEqual(json.loads(lock.read_text())["session"], "B")
        self.assertEqual(self.bulk("next", run, "collect", "--session", "A").returncode, 1)


class PostTests(RunTestCase):
    def decided_run(self, action=None, post="post"):
        run = self.new_run([candidate(12)])
        self.set_item(run, 12, phase="collected")
        assessment_file(run, 12)
        self.bulk_ok("render-item", run, "12")
        args = ["decide", run, "12", "--post", post] + (["--action", action] if action else [])
        self.bulk_ok(*args)
        return run

    def writes(self):
        return [c for c in self.gh_calls() if "POST" in c["args"] or "--method" in c["args"]]

    def test_posts_rendered_text_exactly_then_label(self):
        run = self.decided_run()
        self.gh_rules([recheck_rule(recheck_node(12)), COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
        out = self.bulk_ok("post", run, "12", "--session", "S1")
        self.assertEqual(out, {"number": 12, "comment": "posted", "label": "applied", "reason": None,
                               "comment_url": "https://github.com/acme/widgets/issues/12#issuecomment-77"})
        calls = self.gh_calls()
        comment = [c for c in calls if "repos/acme/widgets/issues/12/comments" in c["args"]][0]
        self.assertEqual(json.loads(comment["input"]), {"body": (run / "items/12/rendered.md").read_text()})
        label = [c for c in calls if "repos/acme/widgets/issues/12/labels" in c["args"]][0]
        self.assertEqual(json.loads(label["input"]), {"labels": ["cc-review:pursue"]})
        self.assertLess(calls.index(comment), calls.index(label))
        self.assertFalse(any("PATCH" in c["args"] or "assignees" in " ".join(c["args"]) for c in calls))
        item = self.item(run, 12)
        self.assertEqual((item["phase"], item["attempt_session"]["post"]), ("done", "S1"))

    def test_fix_choice_keeps_phase_posted(self):
        run = self.decided_run(action="fix")
        self.gh_rules([recheck_rule(recheck_node(12)), COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
        self.bulk_ok("post", run, "12")
        self.assertEqual(self.item(run, 12)["phase"], "posted")

    def test_refuses_when_rendering_changed_since_approval(self):
        run = self.decided_run()
        (run / "items/12/rendered.md").write_text("something else\n")
        self.gh_rules([recheck_rule(recheck_node(12)), COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
        result = self.bulk("post", run, "12", "--session", "S1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: ", result.stderr)
        self.assertEqual(self.gh_calls(), [])
        self.assertEqual(self.item(run, 12)["post"]["comment"], "pending")
        self.assertIsNone(self.bulk_ok("next", run, "post", "--session", "S1")["number"])

    def test_recheck_withholds(self):
        maintainer_pr = {"__typename": "CrossReferencedEvent", "source": {
            "__typename": "PullRequest", "number": 600, "url": "https://github.com/acme/widgets/pull/600",
            "state": "OPEN", "merged": False, "authorAssociation": "MEMBER",
            "author": {"login": "member1", "__typename": "User"}, "baseRepository": {"nameWithOwner": REPO},
            "reviews": {"totalCount": 0, "pageInfo": {"hasPreviousPage": False}, "nodes": []},
            "comments": {"totalCount": 0, "pageInfo": {"hasPreviousPage": False}, "nodes": []}}}
        cases = [("closed", recheck_node(12, state="CLOSED")),
                 ("maintainer", recheck_node(12, comments=[gh_comment("member1", "Looking.", "MEMBER")])),
                 ("assessed", recheck_node(12, comments=[gh_comment(
                     "maint", "Hi\n<!-- cc-review:assessment {} -->\n"
                              "<!-- cc-review:issue-bulk run=20200101-000000-issue -->", "MEMBER")])),
                 ("ci", recheck_node(12, comments=[gh_comment("github-actions[bot]", "x <!-- cc-review:assessment {}",
                                                              typename="Bot")])),
                 ("PR", recheck_node(12, timeline=[maintainer_pr]))]
        reasons = {"closed": "closed after selection", "maintainer": "a maintainer replied after selection",
                   "assessed": "cc-review assessment from another run", "ci": "cc-review assessment from another run",
                   "PR": "a maintainer PR now references it (#600)"}
        for word, node in cases:
            with self.subTest(case=word):
                run = self.decided_run(action="fix")
                self.gh_rules([recheck_rule(node), COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
                out = self.bulk_ok("post", run, "12")
                self.assertEqual((out["comment"], out["label"]), ("withheld", "none"))
                self.assertIn(reasons[word], out["reason"])
                self.assertEqual(self.writes(), [])
                item = self.item(run, 12)
                self.assertEqual(item["phase"], "done")
                self.assertTrue(item["fix"]["abandoned"])

    def test_own_fix_pr_does_not_withhold_a_retried_post(self):
        run = self.decided_run(action="fix")
        own = {"__typename": "CrossReferencedEvent", "source": {
            "__typename": "PullRequest", "number": 601, "url": "https://github.com/acme/widgets/pull/601",
            "state": "OPEN", "merged": False, "headRefName": "cc-review/fix-issue-12", "authorAssociation": "OWNER",
            "author": {"login": "maint", "__typename": "User"}, "baseRepository": {"nameWithOwner": REPO},
            "reviews": {"totalCount": 0, "pageInfo": {"hasPreviousPage": False}, "nodes": []},
            "comments": {"totalCount": 0, "pageInfo": {"hasPreviousPage": False}, "nodes": []}}}
        # Without a push recorded by this run, a PR on the same branch name is someone else's: withheld.
        self.gh_rules([recheck_rule(recheck_node(12, timeline=[own])), COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
        self.assertEqual(self.bulk_ok("post", run, "12")["comment"], "withheld")
        run = self.decided_run(action="fix")
        self.set_item(run, 12, fix={"steps": {"prepared": True, "pushed": True}, "pending": None, "abandoned": None,
                                    "pr_url": "https://github.com/acme/widgets/pull/601"})
        self.gh_rules([recheck_rule(recheck_node(12, timeline=[own])), COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
        self.assertEqual(self.bulk_ok("post", run, "12")["comment"], "posted")
        other = json.loads(json.dumps(own))
        other["source"]["headRefName"] = "someone-else"
        run = self.decided_run(action="fix")
        self.gh_rules([recheck_rule(recheck_node(12, timeline=[other])), COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
        self.assertEqual(self.bulk_ok("post", run, "12")["comment"], "withheld")

    def test_failed_recheck_never_posts(self):
        for rule in ({"match": ["BulkIssueRecheck"], "stderr": "HTTP 502", "exit": 1},
                     {"match": ["BulkIssueRecheck"], "stdout": {"data": {"repository": {"issue": None}}}}):
            with self.subTest(rule=rule):
                run = self.decided_run()
                self.gh_rules([rule, COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
                out = self.bulk_ok("post", run, "12", "--session", "S1")
                self.assertEqual(out["comment"], "failed")
                self.assertIn("Re-check", out["reason"])
                self.assertEqual(self.writes(), [])
                self.assertEqual(self.item(run, 12)["phase"], "decided")
                self.assertEqual(self.bulk_ok("next", run, "post", "--session", "S2")["number"], 12)

    def test_withheld_post_with_open_fix_is_fix_pending_not_posted(self):
        run = self.decided_run(action="fix")
        self.set_item(run, 12, fix={"steps": {"prepared": True, "pushed": True}, "pending": "pr",
                                    "pr_url": None, "abandoned": None})
        self.gh_rules([recheck_rule(recheck_node(12, state="CLOSED"))])
        self.bulk_ok("post", run, "12")
        self.assertEqual(self.item(run, 12)["phase"], "fix_pending")

    def test_withheld_post_keeps_a_pushed_fix(self):
        run = self.decided_run(action="fix")
        self.set_item(run, 12, fix={"steps": {"prepared": True, "pushed": True}, "pending": "pr",
                                    "pr_url": None, "abandoned": None})
        self.gh_rules([recheck_rule(recheck_node(12, state="CLOSED"))])
        self.assertEqual(self.bulk_ok("post", run, "12")["comment"], "withheld")
        fix = self.item(run, 12)["fix"]
        self.assertEqual((fix["pending"], fix["abandoned"]), ("pr", None))

    def test_missing_label_is_not_created(self):
        run = self.decided_run()
        self.gh_rules([recheck_rule(recheck_node(12)), COMMENT_OK,
                       {"match": ["repos/acme/widgets/labels/cc-review%3Apursue"],
                        "stdout": {"message": "Not Found", "status": "404"}, "stderr": "gh: Not Found (HTTP 404)",
                        "exit": 1}, LABEL_ADD])
        out = self.bulk_ok("post", run, "12")
        self.assertEqual((out["comment"], out["label"]), ("posted", "missing"))
        calls = self.gh_calls()
        self.assertFalse(any("repos/acme/widgets/issues/12/labels" in c["args"] for c in calls))
        self.assertFalse(any(c["args"][-1:] == ["repos/acme/widgets/labels"] or "label" == c["args"][0] for c in calls))
        # The only write is the comment: no label is created or added in any request style.
        self.assertEqual([c["args"][3] for c in self.writes()], ["repos/acme/widgets/issues/12/comments"])
        self.assertFalse(any("repos/acme/widgets/labels" in " ".join(c["args"]) and "POST" in c["args"] for c in calls))
        self.assertEqual(self.item(run, 12)["phase"], "done")

    def test_comment_failure_is_recorded_and_retried_next_session(self):
        run = self.decided_run()
        self.gh_rules([recheck_rule(recheck_node(12)),
                       {"match": ["repos/acme/widgets/issues/12/comments"], "stderr": "HTTP 403: rate limit", "exit": 1}])
        out = self.bulk_ok("post", run, "12", "--session", "S1")
        self.assertEqual(out["comment"], "failed")
        self.assertIn("403", out["reason"])
        item = self.item(run, 12)
        self.assertEqual((item["phase"], item["post"]["label"]), ("decided", "pending"))
        self.assertIsNone(self.bulk_ok("next", run, "post", "--session", "S1")["number"])
        self.assertEqual(self.bulk_ok("next", run, "post", "--session", "S2")["number"], 12)

    def test_crash_after_comment_is_not_posted_twice(self):
        run = self.decided_run()
        rendered = (run / "items/12/rendered.md").read_text()
        node = recheck_node(12, comments=[gh_comment("Maint", rendered, "OWNER", cid=55)])
        self.gh_rules([recheck_rule(node), COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
        out = self.bulk_ok("post", run, "12")
        self.assertEqual((out["comment"], out["label"]), ("posted", "applied"))
        self.assertEqual(out["comment_url"], "https://github.com/acme/widgets/issues/12#issuecomment-55")
        self.assertFalse(any("repos/acme/widgets/issues/12/comments" in c["args"] for c in self.gh_calls()))

    def test_failed_label_is_retried_without_new_comment(self):
        run = self.decided_run()
        self.gh_rules([recheck_rule(recheck_node(12)), COMMENT_OK, LABEL_EXISTS,
                       {"match": ["repos/acme/widgets/issues/12/labels"], "stderr": "HTTP 500", "exit": 1}])
        out = self.bulk_ok("post", run, "12", "--session", "S1")
        self.assertEqual((out["comment"], out["label"]), ("posted", "failed"))
        self.assertEqual(self.item(run, 12)["phase"], "decided")
        self.gh_rules([recheck_rule(recheck_node(12)), COMMENT_OK, LABEL_EXISTS, LABEL_ADD])
        out = self.bulk_ok("post", run, "12", "--session", "S2")
        self.assertEqual((out["comment"], out["label"]), ("posted", "applied"))
        self.assertEqual([c for c in self.gh_calls() if "comments" in " ".join(c["args"])], [])
        self.assertFalse(any("BulkIssueRecheck" in " ".join(c["args"]) for c in self.gh_calls()))
        self.assertEqual(self.item(run, 12)["phase"], "done")

    def test_skipped_or_undecided_items_are_not_posted(self):
        run = self.decided_run(post="skip")
        self.assertEqual(self.bulk("post", run, "12").returncode, 1)
        self.assertEqual(self.gh_calls(), [])


def skip(number, reason, pr=None):
    return {"number": number, "url": "https://github.com/acme/widgets/issues/%d" % number,
            "title": "Skipped %d" % number, "reason": reason, "pr": pr}


class ReportTests(RunTestCase):
    def outcome_run(self):
        numbers = [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10]
        cands = [candidate(n, [OPEN_PR] if n == 13 else []) for n in numbers]
        run = self.new_run(cands)
        selection = make_selection(cands, skipped=[skip(30, "maintainer_replied"), skip(31, "maintainer_pr", 501),
                                                   skip(32, "already_assessed"), skip(33, "history_too_long")],
                                   query="repo:acme/widgets is:issue is:open sort:created-desc label:bug")
        selection["ceiling_reached"] = True
        (run / "selection.json").write_text(json.dumps(selection))
        base = {"phase": "done", "recommendation": "pursue", "label": "cc-review:pursue"}
        posted = {"comment": "posted", "comment_url": "https://github.com/acme/widgets/issues/20#issuecomment-1",
                  "label": "applied", "reason": None}
        self.set_item(run, 20, post=posted, decision={"post": "post", "action": None}, **base)
        self.set_item(run, 19, post=dict(posted, comment="failed", label="pending", reason="HTTP 403 forbidden"),
                      decision={"post": "post", "action": None}, **dict(base, phase="decided"))
        self.set_item(run, 18, post=dict(posted, label="missing"), decision={"post": "post", "action": None}, **base)
        self.set_item(run, 17, post={"comment": "skipped", "comment_url": None, "label": "none", "reason": None},
                      decision={"post": "skip", "action": None}, **base)
        self.set_item(run, 16, post={"comment": "withheld", "comment_url": None, "label": "none",
                                     "reason": "The issue was closed after selection."},
                      decision={"post": "post", "action": None}, **base)
        self.set_item(run, 15, phase="assessment_failed", failure="worker wrote no assessment.json")
        self.set_item(run, 14, post=posted, decision={"post": "post", "action": "fix"},
                      fix={"pr_url": "https://github.com/acme/widgets/pull/90", "abandoned": None, "pending": None},
                      **base)
        self.set_item(run, 13, post=posted, decision={"post": "post", "action": "review"}, **base)
        self.set_item(run, 12, post=posted, decision={"post": "post", "action": "fix"},
                      fix={"pr_url": None, "abandoned": "The change exceeds the small bound.", "pending": None},
                      **base)
        self.set_item(run, 11, post=posted, decision={"post": "post", "action": "fix"},
                      fix={"pr_url": None, "abandoned": None, "pending": None}, **dict(base, phase="posted"))
        self.set_item(run, 10, phase="assessed", decision=None)
        load("run_state").update(str(run), lambda st: st["extra"].update(handoff_prs=[505]))
        return run

    def test_run_report_lists_every_outcome_and_coverage(self):
        run = self.outcome_run()
        result = self.bulk("report", run)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = result.stdout
        for number in list(range(10, 21)) + [30, 31, 32, 33]:
            self.assertIn("#%d" % number, text)
        for phrase in ("Posted", "Post failed: HTTP 403 forbidden", "label `cc-review:pursue` missing",
                       "Skipped by maintainer", "Withheld: The issue was closed after selection.",
                       "Assessment failed: worker wrote no assessment.json",
                       "draft PR https://github.com/acme/widgets/pull/90", "handed to review: #505",
                       "fix abandoned: The change exceeds the small bound.",
                       "label:bug", "Scanned: 15", "Selected: 11", "Skipped: 4",
                       "maintainer PR #501", "history too long to verify", "raise --scan"):
            self.assertIn(phrase, text)
        self.assertIn("- Skipped: 4 (already assessed 1, maintainer replied 1, maintainer PR 1, "
                      "history too long to verify 1)", text)
        rows = {int(m.group(1)): line for line in text.splitlines()
                for m in [re.match(r"\| \[#(\d+)\]", line)] if m}
        for number, outcome in ((20, "Posted with label `cc-review:pursue`"), (19, "Post failed: HTTP 403 forbidden"),
                                (18, "label `cc-review:pursue` missing"), (17, "Skipped by maintainer"),
                                (16, "Withheld: The issue was closed after selection."),
                                (15, "Assessment failed: worker wrote no assessment.json"),
                                (14, "draft PR https://github.com/acme/widgets/pull/90"),
                                (13, "linked PRs handed to review: #505"),
                                (12, "fix abandoned: The change exceeds the small bound."),
                                (11, "fix not run yet"), (10, "Waiting for a decision")):
            self.assertIn(outcome, rows[number])
        # #19's failed post is retryable, so the run stays open with the resume command.
        self.assertEqual(self.state(run)["status"], "running")
        self.assertTrue(text.rstrip().endswith("`issue --resume %s`" % run.name), text[-300:])
        self.set_item(run, 19, post={"comment": "posted", "comment_url": "u", "label": "applied", "reason": None},
                      phase="done")
        self.set_item(run, 11, fix={"pr_url": None, "abandoned": "x", "pending": None})
        # #10 still waits for a decision, so the run stays resumable.
        self.assertEqual(self.bulk("report", run).returncode, 0)
        self.assertEqual(self.state(run)["status"], "running")
        self.set_item(run, 10, phase="done", decision={"post": "skip", "action": None},
                      post={"comment": "skipped", "comment_url": None, "label": "none", "reason": None})
        self.assertEqual(self.bulk("report", run).returncode, 0)
        self.assertEqual(self.state(run)["status"], "finished")

    def test_open_fix_keeps_run_open(self):
        run = self.outcome_run()
        self.set_item(run, 19, post={"comment": "posted", "comment_url": "u", "label": "applied", "reason": None},
                      phase="done")
        self.set_item(run, 10, phase="done", decision={"post": "skip", "action": None},
                      post={"comment": "skipped", "comment_url": None, "label": "none", "reason": None})
        text = self.bulk("report", run).stdout
        self.assertIn("fixes for #11", text)
        self.assertEqual(self.state(run)["status"], "running")

    def test_pending_pr_keeps_run_open_with_resume_command(self):
        run = self.outcome_run()
        self.set_item(run, 19, post={"comment": "posted", "comment_url": "u", "label": "applied", "reason": None},
                      phase="done")
        self.set_item(run, 11, fix={"pr_url": None, "abandoned": None, "pending": "pr", "branch": "cc-review/fix-issue-11"})
        result = self.bulk("report", run)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PR pending", result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith("`issue --resume %s`" % run.name), result.stdout[-300:])
        self.assertEqual(self.state(run)["status"], "running")

    def selection_report(self, selection):
        path = self.base / "sel.json"
        path.write_text(json.dumps(selection))
        result = self.bulk("report", "--selection", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_selection_without_matches(self):
        text = self.selection_report(make_selection([], query="repo:acme/widgets is:issue is:open sort:created-desc zzz"))
        self.assertIn("No issues matched", text)
        self.assertIn("zzz", text)

    def test_all_skipped_with_and_without_ceiling(self):
        selection = make_selection([], skipped=[skip(1, "maintainer_replied"), skip(2, "already_assessed"),
                                                skip(3, "maintainer_pr", 9)])
        selection["ceiling_reached"], selection["exhausted"] = True, False
        text = self.selection_report(selection)
        self.assertIn("All 3 candidates were skipped", text)
        self.assertIn("raise --scan", text)
        self.assertNotIn("verified empty", text.replace("not a verified empty", ""))
        for number in (1, 2, 3):
            self.assertIn("#%d" % number, text)
        selection["ceiling_reached"], selection["exhausted"] = False, True
        text = self.selection_report(selection)
        self.assertIn("All 3 candidates were skipped", text)
        self.assertNotIn("raise --scan", text)


HOOK = "#!/bin/sh\necho \"$0\" >> \"%s\"\nexit 0\n"


class FixTestCase(RunTestCase):
    """A real checkout with a bare origin, hooks that must never run, and a decided fix item."""

    def setUp(self):
        super().setUp()
        self.work, self.bare = self.make_repo()
        self.hook_log = self.base / "hooks-ran.log"
        hooks = self.work / ".git/hooks"
        alt = self.base / "repo-hooks"
        alt.mkdir()
        for name in ("post-checkout", "pre-commit", "commit-msg", "prepare-commit-msg", "pre-push", "post-commit",
                     "post-index-change", "reference-transaction", "post-rewrite", "post-merge"):
            for directory in (hooks, alt):
                hook = directory / name
                hook.write_text(HOOK % self.hook_log)
                hook.chmod(0o755)
        # The maintainer works on a feature branch with staged, unstaged and untracked changes, so a stash,
        # checkout, reset or clean by the helper would show.
        git(self.work, "checkout", "-q", "-b", "feature")
        (self.work / "src/staged.py").write_text("staged = True\n")
        git(self.work, "add", "src/staged.py")
        (self.work / "src/app.py").write_text("".join("line %d\n" % i for i in range(1, 51)) + "local edit\n")
        (self.work / "notes.txt").write_text("untracked\n")
        self.before = self.checkout_view()
        self.run = self.new_run([candidate(12)], checkout_root=str(self.work))
        self.set_item(self.run, 12, phase="posted", kind="bug", title="Crash: fixes #3 when @admin runs --fast",
                      decision={"post": "post", "action": "fix", "rendered_sha256": "x"},
                      post={"comment": "posted", "comment_url": "https://github.com/acme/widgets/issues/12#c",
                            "label": "applied", "reason": None})
        git(self.work, "config", "core.hooksPath", str(alt))

    def gh_rules(self, rules):
        # fix-prepare re-reads the issue before a new fix; by default every issue is still open and untouched.
        super().gh_rules(list(rules) + [dict(recheck_rule(recheck_node(n)), match=["BulkIssueRecheck", "number=%d" % n])
                                        for n in range(10, 26)])

    def checkout_view(self):
        return {"branch": git(self.work, "branch", "--show-current"),
                "branches": git(self.work, "branch", "--list"),
                "status": git(self.work, "status", "--porcelain", "--untracked-files=all"),
                "index": git(self.work, "ls-files", "--stage"),
                "head": git(self.work, "rev-parse", "HEAD"),
                "stash": git(self.work, "stash", "list"),
                "app": (self.work / "src/app.py").read_text()}

    def assert_checkout_unchanged(self):
        now = self.checkout_view()
        now["branches"] = "\n".join(line for line in now["branches"].splitlines()
                                    if "cc-review/fix-issue-" not in line) + ("\n" if now["branches"] else "")
        self.assertEqual(now, self.before)

    def assert_no_hooks_or_tools(self):
        self.assertFalse(self.hook_log.exists(), self.hook_log.read_text() if self.hook_log.exists() else "")
        self.assertFalse(self.forbidden.exists())

    def other_clone(self):
        clone = self.base / "other-clone"
        if not clone.exists():
            git(self.base, "clone", "-q", str(self.bare), str(clone))
        return clone

    def fix(self):
        return self.item(self.run, 12)["fix"]


class FixPrepareTests(FixTestCase):
    def test_prepare_creates_isolated_worktree_from_fresh_default_tip(self):
        clone = self.other_clone()
        (clone / "NEWS.md").write_text("news\n")
        git(clone, "add", "-A")
        git(clone, "commit", "-q", "-m", "upstream change")
        git(clone, "push", "-q", "origin", "main")
        tip = git(clone, "rev-parse", "HEAD").strip()
        out = self.bulk_ok("fix-prepare", self.run, "12")
        worktree = self.run / "worktrees/12"
        self.assertEqual(out, {"number": 12, "worktree": str(worktree), "branch": "cc-review/fix-issue-12",
                               "worker_needed": True})
        self.assertEqual(git(worktree, "rev-parse", "HEAD").strip(), tip)
        self.assertEqual(git(worktree, "branch", "--show-current").strip(), "cc-review/fix-issue-12")
        fix = self.fix()
        self.assertEqual((fix["branch"], fix["worktree"], fix["base"]), ("cc-review/fix-issue-12", "worktrees/12", tip))
        self.assertTrue(fix["steps"]["prepared"])
        self.assertFalse(any(fix["steps"][k] for k in ("worker_done", "measured", "committed", "pushed", "pr_opened")))
        self.assertEqual(set(fix["snapshot"]), {"head", "index_sha256", "status_sha256", "branches_sha256",
                                                "git_sha256", "state_sha256", "git_metadata", "status_paths"})
        self.assertEqual(git(self.work, "config", "--get-regexp", "^branch\\.cc-review", check=False), "")
        self.assert_checkout_unchanged()
        self.assert_no_hooks_or_tools()

    def test_prepare_reuses_recorded_worktree(self):
        first = self.bulk_ok("fix-prepare", self.run, "12")
        (self.run / "worktrees/12/src/app.py").write_text("edited\n")
        second = self.bulk_ok("fix-prepare", self.run, "12")
        self.assertEqual(first, second)
        self.assertEqual((self.run / "worktrees/12/src/app.py").read_text(), "edited\n")

    def test_reuse_after_interruption_still_guards_the_checkout(self):
        self.bulk_ok("fix-prepare", self.run, "12")
        # Another item's post changed the run state in between: that alone is fine.
        self.set_item(self.run, 12, attempt_session={"post": "S9"})
        self.assertNotIn("abandoned", self.bulk_ok("fix-prepare", self.run, "12"))
        (self.work / "README.md").write_text("written by an interrupted worker\n")
        out = self.bulk_ok("fix-prepare", self.run, "12")
        self.assertIn("checkout changed during the fix (status: README.md)", out["abandoned"])

    def test_local_branch_conflict_abandons_without_touching_it(self):
        git(self.work, "branch", "cc-review/fix-issue-12")
        out = self.bulk_ok("fix-prepare", self.run, "12")
        self.assertIn("branch conflict", out["abandoned"].lower())
        self.assertFalse((self.run / "worktrees/12").exists())
        self.assertIn("cc-review/fix-issue-12", git(self.work, "branch", "--list"))
        self.assertFalse(self.fix()["steps"]["prepared"])

    def test_remote_branch_conflict_abandons(self):
        clone = self.other_clone()
        git(clone, "push", "-q", "origin", "main:refs/heads/cc-review/fix-issue-12")
        out = self.bulk_ok("fix-prepare", self.run, "12")
        self.assertIn("branch conflict", out["abandoned"].lower())
        self.assertIsNone(self.bulk_ok("next", self.run, "fix")["number"])

    def test_issue_changed_since_assessment_stops_a_new_fix(self):
        contributor = {"__typename": "CrossReferencedEvent", "source": {
            "__typename": "PullRequest", "number": 710, "url": "https://github.com/acme/widgets/pull/710",
            "state": "OPEN", "merged": False, "headRefName": "patch", "authorAssociation": "CONTRIBUTOR",
            "author": {"login": "contrib", "__typename": "User"}, "baseRepository": {"nameWithOwner": REPO},
            "headRepository": {"nameWithOwner": "contrib/widgets"},
            "reviews": {"totalCount": 0, "pageInfo": {"hasPreviousPage": False}, "nodes": []},
            "comments": {"totalCount": 0, "pageInfo": {"hasPreviousPage": False}, "nodes": []}}}
        own_comment = gh_comment("maint", "Reply\n<!-- cc-review:assessment {} -->\n"
                                 + "<!-- cc-review:issue-bulk run=%s -->" % self.run.name, "OWNER")
        cases = [(recheck_node(12, state="CLOSED"), "closed after selection"),
                 (recheck_node(12, timeline=[contributor]), "contributor pull request now references the issue (#710)"),
                 (recheck_node(12, comments=[gh_comment("member1", "On it.", "MEMBER")]), "a maintainer replied"),
                 (recheck_node(12, comments=[own_comment]), None)]
        for node, reason in cases:
            with self.subTest(reason=reason):
                self.set_item(self.run, 12, fix=None)
                git(self.work, "branch", "-D", "cc-review/fix-issue-12", check=False)
                if (self.run / "worktrees/12").exists():
                    git(self.work, "worktree", "remove", "--force", str(self.run / "worktrees/12"))
                self.gh_rules([dict(recheck_rule(node), match=["BulkIssueRecheck", "number=12"])])
                out = self.bulk_ok("fix-prepare", self.run, "12")
                if reason is None:
                    # This run's own posted reply never stops its fix.
                    self.assertTrue(out["worker_needed"], out)
                else:
                    self.assertIn(reason, out["abandoned"])
                    self.assertFalse((self.run / "worktrees/12").exists())

    def test_requires_fix_decision(self):
        self.set_item(self.run, 12, decision={"post": "post", "action": "leave", "rendered_sha256": "x"})
        self.assertEqual(self.bulk("fix-prepare", self.run, "12").returncode, 1)


def lines(count, prefix="x"):
    return "".join("%s %d\n" % (prefix, i) for i in range(count))


class FixMeasureTests(FixTestCase):
    def prepared(self, files, status="done", reason="", summary="Guard the division."):
        self.bulk_ok("fix-prepare", self.run, "12")
        worktree = self.run / "worktrees/12"
        for path, content in files.items():
            target = worktree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content)
        if status is not None:
            (self.run / "items/12").mkdir(parents=True, exist_ok=True)
            (self.run / "items/12/fix.json").write_text(json.dumps({"status": status, "summary": summary,
                                                                     "reason": reason}))
        return worktree

    def measure(self):
        return self.bulk_ok("fix-measure", self.run, "12")

    def test_small_fix_is_measured_and_tree_recorded(self):
        original = "".join("line %d\n" % i for i in range(1, 46))
        worktree = self.prepared({"src/app.py": original + lines(5, "new"), "tests/test_app.py": lines(20)})
        out = self.measure()
        self.assertTrue(out["within_bound"], out)
        self.assertEqual(out["size"], {"files": 1, "lines": 10, "test_lines": 20})
        fix = self.fix()
        self.assertTrue(fix["steps"]["worker_done"] and fix["steps"]["measured"])
        self.assertEqual(fix["tree"], git(worktree, "write-tree").strip())
        self.assertIsNone(fix["abandoned"])
        self.assert_checkout_unchanged()
        self.assert_no_hooks_or_tools()

    def test_bound_boundaries(self):
        cases = [({"a.py": "1\n", "b.py": "2\n", "c.py": "3\n"}, True),
                 ({"a.py": "1\n", "b.py": "2\n", "c.py": "3\n", "d.py": "4\n"}, False),
                 ({"big.py": lines(100)}, True), ({"big.py": lines(101)}, False),
                 ({"tests/test_big.py": lines(300)}, True), ({"tests/test_big.py": lines(301)}, False),
                 ({"logo.png": b"\x89PNG\x00\x01\x02", "a.py": "1\n"}, False),
                 ({"logo.png": b"\x89PNG\x00\x01\x02"}, False)]
        for files, inside in cases:
            with self.subTest(files=sorted(files)):
                self.tearDown_fix()
                self.prepared(files)
                out = self.measure()
                self.assertEqual(out["within_bound"], inside, out)
                if not inside:
                    # Any binary file abandons the fix, whatever its size.
                    expected = "Binary change: the fix changes logo.png" if "logo.png" in files else "small bound"
                    self.assertIn(expected, out["reason"])
                    self.assertIn(expected, self.fix()["abandoned"])

    def tearDown_fix(self):
        worktree = self.run / "worktrees/12"
        if worktree.exists():
            git(self.work, "worktree", "remove", "--force", str(worktree))
        git(self.work, "branch", "-D", "cc-review/fix-issue-12", check=False)
        self.set_item(self.run, 12, fix=None)
        fix_json = self.run / "items/12/fix.json"
        if fix_json.exists():
            fix_json.unlink()

    def test_test_file_classification(self):
        bulk = load("issue_bulk")
        tests = ["test/a.c", "tests/b.py", "spec/c.rb", "src/__tests__/d.js", "pkg/e_test.go", "test_f.py",
                 "src/g.test.ts", "src/h.spec.js", "deep/tests/x/y.txt"]
        others = ["src/contest.py", "latest/a.py", "src/testing.py", "attest/b.py", "test.py", "spec.md",
                  "src/tests.py"]
        for path in tests:
            self.assertTrue(bulk.is_test_path(path), path)
        for path in others:
            self.assertFalse(bulk.is_test_path(path), path)

    def test_no_change_gave_up_or_missing_result_abandons(self):
        self.prepared({})
        self.assertIn("no change", self.measure()["reason"])
        self.tearDown_fix()
        self.prepared({"src/app.py": "x\n"}, status="gave_up", reason="The change needs a new module.")
        out = self.measure()
        self.assertFalse(out["within_bound"])
        self.assertIn("The change needs a new module.", out["reason"])
        self.tearDown_fix()
        self.prepared({"src/app.py": "x\n"}, status=None)
        self.assertIn("fix.json", self.measure()["reason"])

    def test_outside_worktree_changes_abandon(self):
        edits = [lambda: (self.work / "README.md").write_text("changed by worker\n"),
                 lambda: (self.work / "stray.txt").write_text("new\n"),
                 lambda: git(self.work, "branch", "worker-branch"),
                 lambda: self.set_item(self.run, 12, decision={"post": "post", "action": "fix",
                                                               "rendered_sha256": "forged"})]
        for edit, changed in zip(edits, ("status: README.md", "status: stray.txt", "branches", "state")):
            with self.subTest(changed=changed):
                self.tearDown_fix()
                self.set_item(self.run, 12, decision={"post": "post", "action": "fix", "rendered_sha256": "x"})
                self.prepared({"src/app.py": lines(45)})
                edit()
                out = self.measure()
                self.assertFalse(out["within_bound"])
                self.assertIn("The checkout changed during the fix (", out["reason"])
                self.assertIn(changed, out["reason"])
                git(self.work, "checkout", "--", "README.md")
                for leftover in (self.work / "stray.txt",):
                    if leftover.exists():
                        leftover.unlink()
                git(self.work, "branch", "-D", "worker-branch", check=False)

    def test_worker_rewriting_its_fix_record_abandons_and_never_touches_main(self):
        self.prepared({"src/app.py": lines(45)})
        fix = self.fix()
        fix.update(branch="main", worktree=str(self.work))
        self.set_item(self.run, 12, fix=fix)
        out = self.measure()
        self.assertFalse(out["within_bound"])
        self.assertIn("changed during the fix (state)", out["reason"])
        self.bulk_ok("fix-cleanup", self.run, "12")
        # Cleanup derives the branch and worktree from the issue number, never from the tampered record.
        self.assertIn("main", git(self.work, "branch", "--list"))
        self.assertTrue((self.work / "README.md").exists())
        self.assertNotIn("cc-review/fix-issue-12", git(self.work, "branch", "--list"))

    def test_dirty_file_edited_again_abandons(self):
        self.prepared({"src/app.py": lines(45)})
        (self.work / "src/app.py").write_text("worker edit of an already modified file\n")
        out = self.measure()
        self.assertFalse(out["within_bound"])
        self.assertIn("status: src/app.py", out["reason"])
        (self.work / "src/app.py").write_text(self.before["app"])

    def test_redirected_gitdir_never_runs_planted_config(self):
        worktree = self.prepared({"src/app.py": lines(45)})
        marker = self.base / "PWNED"
        evil = worktree / ".evil"
        (evil / "objects/info").mkdir(parents=True)
        (evil / "refs").mkdir()
        (evil / "HEAD").write_text(git(self.work, "rev-parse", "HEAD"))
        (evil / "objects/info/alternates").write_text(str(self.work / ".git/objects") + "\n")
        (evil / "config").write_text('[core]\n\trepositoryformatversion = 0\n\tfsmonitor = "touch %s; false"\n'
                                     % marker)
        (worktree / ".git").write_text("gitdir: .evil\n")
        out = self.measure()
        self.assertFalse(out["within_bound"])
        self.assertIn("no git command was run", out["reason"])
        self.assertTrue(self.fix()["tainted"])
        self.assertFalse(marker.exists())
        cleanup = self.bulk_ok("fix-cleanup", self.run, "12")
        self.assertFalse(cleanup["cleaned"])
        self.assertFalse(marker.exists())
        self.assertIsNone(self.bulk_ok("next", self.run, "fix")["number"])

    def test_worker_commit_is_never_published(self):
        worktree = self.prepared({"src/app.py": lines(45)})
        git(worktree, "add", "-A")
        git(worktree, "commit", "-q", "--no-verify", "-m", "fixes #3 @admin")
        out = self.measure()
        self.assertFalse(out["within_bound"])
        self.assertIn("base commit", out["reason"])
        self.assertFalse(git(self.work, "ls-remote", "--heads", "origin", "refs/heads/cc-review/fix-issue-12").strip())

    def test_taint_stops_every_later_git_step_of_the_run(self):
        # A planted remote.origin.uploadpack runs on any fetch, so the next fix's prepare must run no git.
        self.run = self.new_run([candidate(12), candidate(13)], checkout_root=str(self.work))
        for n in (12, 13):
            self.set_item(self.run, n, phase="posted", kind="bug", title="Bug %d" % n,
                          decision={"post": "post", "action": "fix", "rendered_sha256": "x"},
                          post={"comment": "posted", "comment_url": "u", "label": "applied", "reason": None})
        self.prepared({"src/app.py": lines(45)})
        marker = self.base / "PWNED"
        with open(self.work / ".git/config", "a") as stream:
            stream.write('[remote "origin"]\n\tuploadpack = "touch %s; git-upload-pack"\n' % marker)
        self.assertIn("no further git command", self.measure()["reason"])
        out = self.bulk_ok("fix-prepare", self.run, "13")
        self.assertIn("no further git command", out["abandoned"])
        self.assertFalse(marker.exists())
        self.assertFalse((self.run / "worktrees/13").exists())
        self.assertIsNone(self.bulk_ok("next", self.run, "fix")["number"])
        self.assertFalse(self.bulk_ok("fix-cleanup", self.run, "12")["cleaned"])
        left = self.bulk_ok("abandon-run", self.run)
        self.assertEqual(left["cleaned"], [])
        self.assertFalse(marker.exists())
        self.assertIn("Fixes stopped", self.bulk("report", self.run).stdout)

    def test_changed_configuration_stops_publishing(self):
        PublishTestCase.measured(self)
        git(self.work, "config", "remote.origin.pushurl", str(self.base / "elsewhere.git"))
        out = self.bulk_ok("fix-publish", self.run, "12")
        self.assertIn("no further git command", out["abandoned"])
        self.assertFalse(self.fix()["steps"]["committed"])

    def test_planted_repository_config_is_detected_before_git_runs(self):
        self.prepared({"src/app.py": lines(45)})
        marker = self.base / "PWNED"
        with open(self.work / ".git/config", "a") as stream:
            stream.write('[core]\n\tfsmonitor = "touch %s; false"\n' % marker)
        out = self.measure()
        self.assertIn("no further git command", out["reason"])
        self.assertTrue(self.fix()["tainted"])
        self.assertFalse(marker.exists())


PR_URL = "https://github.com/acme/widgets/pull/77"
PR_LIST_EMPTY = {"match": ["pr", "list", "--head", "cc-review/fix-issue-12"], "stdout": "[]"}
PR_CREATE = {"match": ["pr", "create", "--draft"], "stdout": PR_URL}


class PublishTestCase(FixTestCase):
    prepared = FixMeasureTests.prepared
    tearDown_fix = FixMeasureTests.tearDown_fix

    def measured(self, summary="Guard the division. Fixes #3 too, thanks @admin <b>!</b>"):
        original = "".join("line %d\n" % i for i in range(1, 46))
        worktree = self.prepared({"src/app.py": original + lines(5, "new")}, summary=summary)
        self.assertTrue(self.bulk_ok("fix-measure", self.run, "12")["within_bound"])
        return worktree

    def remote_branch(self):
        return git(self.work, "ls-remote", "--heads", "origin", "refs/heads/cc-review/fix-issue-12").strip()


class FixPublishTests(PublishTestCase):
    def test_publish_commits_pushes_and_opens_draft_pr(self):
        worktree = self.measured()
        self.gh_rules([PR_LIST_EMPTY, PR_CREATE])
        out = self.bulk_ok("fix-publish", self.run, "12", "--session", "S1")
        self.assertEqual(out, {"number": 12, "pr_url": PR_URL, "pending": None, "abandoned": None})
        subject = git(worktree, "log", "-1", "--format=%s").strip()
        self.assertEqual(subject, "fix: Crash: see #3 when @admin runs --fast (#12)")
        self.assertEqual(git(worktree, "log", "-1", "--format=%an <%ae>").strip(),
                         "Maintainer <maintainer@example.com>")
        self.assertTrue(self.remote_branch())
        fix = self.fix()
        self.assertTrue(all(fix["steps"][k] for k in ("committed", "pushed", "pr_opened")))
        self.assertEqual((fix["pr_url"], fix["pending"], fix["commit"]),
                         (PR_URL, None, git(worktree, "rev-parse", "HEAD").strip()))
        self.assertEqual(self.item(self.run, 12)["attempt_session"]["fix"], "S1")
        create = [c for c in self.gh_calls() if c["args"][:2] == ["pr", "create"]][0]
        args = create["args"]
        for flag, value in (("--repo", REPO), ("--base", "main"), ("--head", "cc-review/fix-issue-12"),
                            ("--title", subject)):
            self.assertEqual(args[args.index(flag) + 1], value)
        self.assertIn("--draft", args)
        body = create["body_file"]
        self.assertIn("Fixes #12", body)
        self.assertIn("Tests were not run locally; the repository's checks on this pull request run them.", body)
        self.assertNotRegex(body.replace("Fixes #12", ""), r"(?i)\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s*:?\s*#\d")
        self.assertIn("&#64;admin", body)
        self.assertIn("&lt;b&gt;", body)
        self.assertEqual((self.run / "items/12/pr-body.md").read_text(), body)
        self.assert_checkout_unchanged()
        self.assert_no_hooks_or_tools()

    def test_worktree_changed_after_measuring_abandons(self):
        worktree = self.measured()
        (worktree / "src/app.py").write_text("sneaky\n")
        git(worktree, "add", "-A")
        self.gh_rules([PR_LIST_EMPTY, PR_CREATE])
        out = self.bulk_ok("fix-publish", self.run, "12")
        self.assertIn("changed after measuring", out["abandoned"])
        self.assertFalse(self.remote_branch())
        self.assertEqual(self.gh_calls(), [])

    def test_commit_failure_abandons(self):
        self.measured()
        # A stale lock on the fix branch ref makes the commit fail.
        Path(self.fix()["common_dir"], "refs/heads/cc-review/fix-issue-12.lock").write_text("")
        out = self.bulk_ok("fix-publish", self.run, "12")
        self.assertIn("commit failed", out["abandoned"].lower())
        self.assertFalse(self.remote_branch())

    def test_rejected_push_stays_pending_and_is_retried(self):
        self.measured()
        hook = self.bare / "hooks/pre-receive"  # the remote side refuses; origin stays reachable
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        out = self.bulk_ok("fix-publish", self.run, "12", "--session", "S1")
        self.assertEqual((out["abandoned"], out["pending"]), (None, "push"))
        fix = self.fix()
        self.assertTrue(fix["steps"]["committed"])
        self.assertIn("Push failed", fix["pr_error"])
        self.bulk_ok("fix-cleanup", self.run, "12", "--session", "S1")
        self.assertNotIn("cc-review/fix-issue-12", git(self.work, "branch", "--list"))
        self.assertIn("push pending", self.bulk("report", self.run).stdout)
        self.assertEqual(self.state(self.run)["status"], "running")
        hook.unlink()
        self.assertEqual(self.bulk_ok("next", self.run, "fix", "--session", "S2")["number"], 12)
        self.gh_rules([PR_LIST_EMPTY, PR_CREATE])
        self.assertEqual(self.bulk_ok("fix-publish", self.run, "12", "--session", "S2")["pr_url"], PR_URL)
        self.assertEqual(self.remote_branch().split()[0], fix["commit"])

    def test_push_url_elsewhere_is_refused(self):
        bulk = load("issue_bulk")
        self.assertTrue(bulk.github_url_of("git@github.com:acme/widgets.git", REPO))
        self.assertFalse(bulk.github_url_of("https://github.com/other/widgets", REPO))
        # A push URL the maintainer configured before the fix pass that points at another repository.
        git(self.work, "config", "remote.origin.pushurl", "https://github.com/other/widgets.git")
        self.measured()
        out = self.bulk_ok("fix-publish", self.run, "12")
        self.assertIn("origin pushes to https://github.com/other/widgets.git", out["abandoned"])
        self.assertFalse(self.remote_branch())

    def test_unconfirmed_push_stays_resumable(self):
        self.measured()
        moved = self.base / "moved-origin.git"
        self.bare.rename(moved)
        out = self.bulk_ok("fix-publish", self.run, "12", "--session", "S1")
        self.assertEqual((out["abandoned"], out["pending"], out["pr_url"]), (None, "push", None))
        self.assertIn("Push not confirmed", self.fix()["pr_error"])
        self.assertIsNone(self.bulk_ok("next", self.run, "fix", "--session", "S1")["number"])
        moved.rename(self.bare)
        self.gh_rules([PR_LIST_EMPTY, PR_CREATE])
        self.assertEqual(self.bulk_ok("fix-publish", self.run, "12", "--session", "S2")["pr_url"], PR_URL)
        self.assertTrue(self.remote_branch())

    def test_pr_failure_stays_pending_then_adopts_existing_pr(self):
        worktree = self.measured()
        self.gh_rules([PR_LIST_EMPTY, {"match": ["pr", "create"], "stderr": "HTTP 502", "exit": 1}])
        out = self.bulk_ok("fix-publish", self.run, "12", "--session", "S1")
        self.assertEqual((out["pr_url"], out["pending"], out["abandoned"]), (None, "pr", None))
        fix = self.fix()
        self.assertTrue(fix["steps"]["pushed"])
        self.assertFalse(fix["steps"]["pr_opened"])
        self.assertIsNone(self.bulk_ok("next", self.run, "fix", "--session", "S1")["number"])
        self.assertEqual(self.bulk_ok("next", self.run, "fix", "--session", "S2")["number"], 12)
        head = git(worktree, "rev-parse", "HEAD").strip()
        self.gh_rules([{"match": ["pr", "list", "--head", "cc-review/fix-issue-12"],
                        "stdout": json.dumps([{"url": PR_URL}])}, PR_CREATE])
        out = self.bulk_ok("fix-publish", self.run, "12", "--session", "S2")
        self.assertEqual(out["pr_url"], PR_URL)
        self.assertFalse(any(c["args"][:2] == ["pr", "create"] for c in self.gh_calls()))
        self.assertEqual(git(worktree, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(git(worktree, "rev-list", "--count", "HEAD").strip(), "2")

    def test_sanitizer_neutralizes_references_mentions_and_html(self):
        bulk = load("issue_bulk")
        text = bulk.sanitize_summary(
            "Fixes #3. Also closes acme/other#4 and Resolved: https://github.com/acme/widgets/issues/5. "
            "fixes#6. See #7 and `fixes #9` in code. Ping @admin. <img src=x>")
        self.assertNotRegex(text, r"(?i)\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b\s*:?\s*"
                                  r"(#\d|acme/other#\d|https://github\.com/\S+/issues/\d)")
        self.assertIn("See #7", text)
        # No code-span exception: a reference inside backticks is neutralized too.
        self.assertIn("`see #9`", text)
        self.assertIn("&#64;admin", text)
        self.assertNotIn("@admin", text)
        self.assertIn("&lt;img src=x&gt;", text)
        self.assertLessEqual(len(bulk.sanitize_summary("word " * 1000)), 1500)
        self.assertEqual(bulk.commit_subject({"kind": "feature", "title": "x" * 200}, "4"),
                         "feat: " + "x" * 72 + " (#4)")
        self.assertTrue(bulk.commit_subject({"kind": "question", "title": "Why?"}, "4").startswith("chore: "))

    def test_unbalanced_backticks_do_not_hide_references(self):
        bulk = load("issue_bulk")
        for raw in ("Refactor ` @octocat and fixes #7 `` done <b>", "x \\`fixes #7 @octocat` <b>"):
            text = bulk.sanitize_summary(raw)
            self.assertNotIn("@octocat", text)
            self.assertNotRegex(text, r"(?i)fixes #7")
            self.assertIn("&lt;b&gt;", text)
        subject = bulk.commit_subject({"kind": "bug", "title": "Crash `closes #3` here"}, "12")
        self.assertNotRegex(subject, r"(?i)closes #3")


class FixCleanupTests(PublishTestCase):
    def test_full_fix_leaves_checkout_and_branch_list_unchanged(self):
        branches_before = git(self.work, "branch", "--list")
        status_before = git(self.work, "status", "--porcelain", "--untracked-files=all")
        self.measured()
        self.gh_rules([PR_LIST_EMPTY, PR_CREATE])
        self.bulk_ok("fix-publish", self.run, "12")
        self.assertEqual(self.bulk_ok("fix-cleanup", self.run, "12"), {"number": 12, "cleaned": True})
        self.assertEqual(git(self.work, "branch", "--list"), branches_before)
        self.assertEqual(git(self.work, "status", "--porcelain", "--untracked-files=all"), status_before)
        self.assertFalse((self.run / "worktrees/12").exists())
        self.assertNotIn("worktrees/12", git(self.work, "worktree", "list"))
        self.assertTrue(self.remote_branch())
        self.assertEqual(self.item(self.run, 12)["phase"], "done")
        self.assertIsNone(self.bulk_ok("next", self.run, "fix")["number"])
        self.assert_no_hooks_or_tools()

    def test_abandoned_fix_is_cleaned_without_push(self):
        self.prepared({"big.py": lines(101)})
        self.assertFalse(self.bulk_ok("fix-measure", self.run, "12")["within_bound"])
        self.assertEqual(self.bulk_ok("next", self.run, "fix")["number"], 12)
        self.bulk_ok("fix-cleanup", self.run, "12")
        self.assertFalse((self.run / "worktrees/12").exists())
        self.assertNotIn("cc-review/fix-issue-12", git(self.work, "branch", "--list"))
        self.assertFalse(self.remote_branch())
        self.assertIsNone(self.bulk_ok("next", self.run, "fix")["number"])
        self.assert_checkout_unchanged()

    def test_pending_pr_cleans_the_checkout_and_opens_later(self):
        self.measured()
        self.gh_rules([PR_LIST_EMPTY, {"match": ["pr", "create"], "stderr": "HTTP 502", "exit": 1}])
        self.bulk_ok("fix-publish", self.run, "12", "--session", "S1")
        out = self.bulk_ok("fix-cleanup", self.run, "12", "--session", "S1")
        self.assertTrue(out["cleaned"])
        self.assertFalse((self.run / "worktrees/12").exists())
        self.assertNotIn("cc-review/fix-issue-12", git(self.work, "branch", "--list"))
        self.assertTrue(self.remote_branch())
        self.assertNotEqual(self.item(self.run, 12)["phase"], "done")
        self.assert_checkout_unchanged()
        self.assertIsNone(self.bulk_ok("next", self.run, "fix", "--session", "S1")["number"])
        self.assertEqual(self.bulk_ok("next", self.run, "fix", "--session", "S2")["number"], 12)
        prepared = self.bulk_ok("fix-prepare", self.run, "12", "--session", "S2")
        self.assertFalse(prepared["worker_needed"])
        self.assertFalse((self.run / "worktrees/12").exists())
        self.assertTrue(self.bulk_ok("fix-measure", self.run, "12")["within_bound"])
        self.gh_rules([PR_LIST_EMPTY, PR_CREATE])
        self.assertEqual(self.bulk_ok("fix-publish", self.run, "12", "--session", "S2")["pr_url"], PR_URL)
        self.bulk_ok("fix-cleanup", self.run, "12", "--session", "S2")
        self.assertEqual(self.item(self.run, 12)["phase"], "done")
        self.assertEqual(self.bulk("report", self.run).returncode, 0)
        self.assertEqual(self.state(self.run)["status"], "finished")

    def test_conflicting_branch_is_never_deleted(self):
        git(self.work, "branch", "cc-review/fix-issue-12")
        self.bulk_ok("fix-prepare", self.run, "12")
        self.bulk_ok("fix-cleanup", self.run, "12")
        self.assertIn("cc-review/fix-issue-12", git(self.work, "branch", "--list"))
        self.assertEqual(self.item(self.run, 12)["phase"], "done")

    def test_failed_post_keeps_item_open_for_retry(self):
        self.set_item(self.run, 12, phase="decided",
                      post={"comment": "failed", "comment_url": None, "label": "pending", "reason": "HTTP 500"})
        self.prepared({"big.py": lines(101)})
        self.bulk_ok("fix-measure", self.run, "12")
        self.bulk_ok("fix-cleanup", self.run, "12")
        self.assertEqual(self.item(self.run, 12)["phase"], "decided")
        self.assertEqual(self.bulk_ok("next", self.run, "post")["number"], 12)


PR_OPEN_505 = {"match": ["repos/acme/widgets/pulls/505"], "stdout": {"number": 505, "state": "open"}}


class HandoffTests(RunTestCase):
    def review_run(self):
        other = dict(OPEN_PR, number=507, url="https://github.com/acme/widgets/pull/507")
        run = self.new_run([candidate(12, [OPEN_PR, CLOSED_PR]), candidate(11, [other]), candidate(10)])
        posted = {"comment": "posted", "comment_url": "u", "label": "applied", "reason": None}
        self.set_item(run, 12, phase="done", post=posted, decision={"post": "post", "action": "review"})
        self.set_item(run, 11, phase="done", post=posted, decision={"post": "post", "action": "leave"})
        self.set_item(run, 10, phase="done", post=posted, decision={"post": "post", "action": None})
        return run

    def setUp(self):
        super().setUp()
        self.gh_rules([PR_OPEN_505])

    def test_record_handoff_and_report(self):
        run = self.review_run()
        out = self.bulk_ok("record-handoff", run, "505")
        self.assertEqual(out, {"handoff_prs": [505], "repository": REPO, "command": "review --bulk --prs 505",
                               "closed": []})
        self.assertEqual(self.state(run)["extra"]["handoff_prs"], [505])
        text = self.bulk("report", run).stdout
        self.assertIn("linked PRs handed to review: #505", text)
        self.assertIn("`review --bulk --prs 505`", text)

    def test_only_open_linked_prs_of_review_items(self):
        run = self.review_run()
        for value in ("506", "507", "999", "505,507"):
            with self.subTest(value=value):
                result = self.bulk("record-handoff", run, value)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Error: ", result.stderr)
        for value in ("abc", "", "5,,6", "-5"):
            with self.subTest(value=value):
                self.assertEqual(self.bulk("record-handoff", run, value).returncode, 2)
        self.assertEqual(self.state(run)["extra"]["handoff_prs"], [])

    def test_default_list_is_computed_by_the_helper(self):
        run = self.review_run()
        self.assertEqual(self.bulk_ok("record-handoff", run),
                         {"handoff_prs": [505], "repository": REPO, "command": "review --bulk --prs 505",
                          "closed": []})
        self.assertEqual(self.state(run)["extra"]["handoff_prs"], [505])
        empty = self.new_run([candidate(10)])
        self.assertEqual(self.bulk_ok("record-handoff", empty)["command"], None)

    def test_pr_closed_since_selection_is_not_handed_off(self):
        run = self.review_run()
        self.gh_rules([{"match": ["repos/acme/widgets/pulls/505"], "stdout": {"number": 505, "state": "closed"}}])
        out = self.bulk_ok("record-handoff", run)
        self.assertEqual((out["handoff_prs"], out["command"], out["closed"]), ([], None, [505]))
        self.assertEqual(self.state(run)["extra"]["handoff_prs"], [])

    def test_duplicates_are_recorded_once(self):
        run = self.review_run()
        self.assertEqual(self.bulk_ok("record-handoff", run, "505,505")["handoff_prs"], [505])


class ResumeTests(PublishTestCase):
    """An interrupted run: A posted, B assessed, C pushed without PR, D prepared, E measured."""

    def setUp(self):
        super().setUp()
        self.run = self.new_run([candidate(n) for n in (20, 19, 18, 17, 16, 15)],
                                checkout_root=str(self.work))
        posted = {"comment": "posted", "comment_url": "https://github.com/acme/widgets/issues/20#issuecomment-5",
                  "label": "applied", "reason": None}
        fix = {"post": "post", "action": "fix", "rendered_sha256": "x"}
        self.set_item(self.run, 20, phase="done", post=posted, label="cc-review:pursue",
                      decision={"post": "post", "action": "leave", "rendered_sha256": "x"})
        self.set_item(self.run, 19, phase="collected")
        assessment_file(self.run, 19)
        self.bulk_ok("render-item", self.run, "19")
        for n in (18, 17, 16):
            self.set_item(self.run, n, phase="posted", post=posted, decision=fix, kind="bug", title="Bug %d" % n,
                          label="cc-review:pursue")
        # 15: the comment reached GitHub, then the session died before the state write.
        self.set_item(self.run, 15, phase="collected")
        assessment_file(self.run, 15)
        self.bulk_ok("render-item", self.run, "15")
        self.bulk_ok("decide", self.run, "15", "--post", "post")
        self.c_head = self.stage(18, publish=True)
        self.stage(17, edit=False)
        self.e_tree = self.stage(16)

    def stage(self, n, edit=True, publish=False):
        key = str(n)
        self.bulk_ok("fix-prepare", self.run, key)
        if not edit:
            return None
        worktree = self.run / "worktrees" / key
        (worktree / "src/app.py").write_text("".join("line %d\n" % i for i in range(1, 46)) + lines(5, "fix"))
        (self.run / "items" / key).mkdir(parents=True, exist_ok=True)
        (self.run / "items" / key / "fix.json").write_text(json.dumps({"status": "done", "summary": "Fix " + key,
                                                                       "reason": ""}))
        self.assertTrue(self.bulk_ok("fix-measure", self.run, key)["within_bound"])
        if publish:
            self.gh_rules([{"match": ["pr", "list"], "stdout": "[]"},
                           {"match": ["pr", "create"], "stderr": "HTTP 502", "exit": 1}])
            self.assertEqual(self.bulk_ok("fix-publish", self.run, key, "--session", "OLD")["pending"], "pr")
            return git(worktree, "rev-parse", "HEAD").strip()
        return git(worktree, "write-tree").strip()

    def remote(self, n):
        return git(self.work, "ls-remote", "--heads", "origin", "refs/heads/cc-review/fix-issue-%d" % n).strip()

    def test_decisions_continue_without_reassessment(self):
        self.assertIsNone(self.bulk_ok("next", self.run, "collect")["number"])
        self.assertIsNone(self.bulk_ok("next", self.run, "assess")["number"])
        self.assertEqual(self.bulk_ok("next", self.run, "decide")["number"], 19)

    def test_posted_issue_is_never_posted_again(self):
        self.gh_rules([])
        out = self.bulk_ok("post", self.run, "20", "--session", "NEW")
        self.assertEqual((out["comment"], out["label"]), ("posted", "applied"))
        self.assertEqual(self.gh_calls(), [])

    def test_comment_found_by_run_marker_is_not_duplicated(self):
        rendered = (self.run / "items/15/rendered.md").read_text()
        node = recheck_node(15, comments=[gh_comment("maint", rendered, "OWNER", number=15, cid=9)])
        self.gh_rules([recheck_rule(node),
                       {"match": ["repos/acme/widgets/labels/cc-review%3Apursue"], "stdout": {"name": "x"}},
                       {"match": ["repos/acme/widgets/issues/15/labels"], "stdout": "[]"}])
        self.assertEqual(self.bulk_ok("next", self.run, "post", "--session", "NEW")["number"], 15)
        out = self.bulk_ok("post", self.run, "15", "--session", "NEW")
        self.assertEqual(out["comment"], "posted")
        self.assertFalse(any("issues/15/comments" in " ".join(c["args"]) for c in self.gh_calls()))

    def test_prepared_worktree_is_reused(self):
        worktree = self.run / "worktrees/17"
        (worktree / "keep.txt").write_text("partial work\n")
        out = self.bulk_ok("fix-prepare", self.run, "17")
        self.assertEqual(out["worktree"], str(worktree))
        self.assertEqual((worktree / "keep.txt").read_text(), "partial work\n")

    def test_measured_fix_commits_and_pushes_once(self):
        self.assertFalse(self.remote(16))
        self.gh_rules([{"match": ["pr", "list"], "stdout": "[]"}, {"match": ["pr", "create"],
                       "stdout": "https://github.com/acme/widgets/pull/81"}])
        out = self.bulk_ok("fix-publish", self.run, "16", "--session", "NEW")
        self.assertEqual(out["pr_url"], "https://github.com/acme/widgets/pull/81")
        worktree = self.run / "worktrees/16"
        self.assertEqual(git(worktree, "rev-list", "--count", "HEAD").strip(), "2")
        self.assertEqual(git(worktree, "rev-parse", "HEAD^{tree}").strip(), self.e_tree)
        self.assertEqual(self.remote(16).split()[0], git(worktree, "rev-parse", "HEAD").strip())
        again = self.bulk_ok("fix-publish", self.run, "16", "--session", "LATER")
        self.assertEqual(again["pr_url"], out["pr_url"])
        self.assertEqual(git(worktree, "rev-list", "--count", "HEAD").strip(), "2")
        self.assertEqual(len([c for c in self.gh_calls() if c["args"][:2] == ["pr", "create"]]), 1)

    def test_commit_made_before_interruption_is_adopted(self):
        worktree = self.run / "worktrees/16"
        git(worktree, "commit", "-q", "--no-verify", "-m", "fix: Bug 16 (#16)")
        head = git(worktree, "rev-parse", "HEAD").strip()
        self.gh_rules([{"match": ["pr", "list"], "stdout": "[]"},
                       {"match": ["pr", "create"], "stdout": "https://github.com/acme/widgets/pull/82"}])
        out = self.bulk_ok("fix-publish", self.run, "16", "--session", "NEW")
        self.assertEqual(out["pr_url"], "https://github.com/acme/widgets/pull/82")
        self.assertEqual(self.item(self.run, 16)["fix"]["commit"], head)
        self.assertEqual(self.remote(16).split()[0], head)

    def test_finished_worker_is_not_dispatched_again(self):
        self.assertFalse(self.bulk_ok("fix-prepare", self.run, "16", "--session", "NEW")["worker_needed"])
        self.assertFalse(self.bulk_ok("fix-prepare", self.run, "18", "--session", "NEW")["worker_needed"])
        self.assertTrue(self.bulk_ok("fix-prepare", self.run, "17", "--session", "NEW")["worker_needed"])

    def test_abandon_run_removes_fix_worktrees_and_branches(self):
        out = self.bulk_ok("abandon-run", self.run)
        self.assertEqual(out["status"], "abandoned")
        self.assertEqual(sorted(out["cleaned"]), [16, 17, 18])
        self.assertEqual(out["pushed_without_pr"], ["cc-review/fix-issue-18"])
        self.assertNotIn("cc-review/fix-issue-", git(self.work, "branch", "--list"))
        self.assertEqual(list((self.run / "worktrees").iterdir()), [])
        self.assertEqual(self.state(self.run)["status"], "abandoned")
        self.assert_checkout_unchanged()

    def test_pushed_fix_only_opens_the_pr(self):
        remote_before = self.remote(18)
        self.assertEqual(self.bulk_ok("next", self.run, "fix", "--session", "NEW")["number"], 18)
        self.gh_rules([{"match": ["pr", "list"], "stdout": "[]"},
                       {"match": ["pr", "create"], "stdout": "https://github.com/acme/widgets/pull/80"}])
        out = self.bulk_ok("fix-publish", self.run, "18", "--session", "NEW")
        self.assertEqual(out["pr_url"], "https://github.com/acme/widgets/pull/80")
        worktree = self.run / "worktrees/18"
        self.assertEqual(git(worktree, "rev-parse", "HEAD").strip(), self.c_head)
        self.assertEqual(self.remote(18), remote_before)
        creates = [c for c in self.gh_calls() if c["args"][:2] == ["pr", "create"]]
        self.assertEqual(len(creates), 1)

    def test_existing_open_pr_is_adopted(self):
        self.gh_rules([{"match": ["pr", "list", "cc-review/fix-issue-18"],
                        "stdout": json.dumps([{"url": "https://github.com/acme/widgets/pull/79"}])},
                       {"match": ["pr", "create"], "stdout": "https://github.com/acme/widgets/pull/99"}])
        out = self.bulk_ok("fix-publish", self.run, "18", "--session", "NEW")
        self.assertEqual(out["pr_url"], "https://github.com/acme/widgets/pull/79")
        self.assertFalse(any(c["args"][:2] == ["pr", "create"] for c in self.gh_calls()))
        self.assertEqual(self.bulk_ok("fix-cleanup", self.run, "18")["cleaned"], True)
        self.assertNotEqual(self.bulk_ok("next", self.run, "fix", "--session", "NEW2")["number"], 18)


def load(name):
    module = importlib.import_module(name)
    return importlib.reload(module)


if __name__ == "__main__":
    unittest.main()
