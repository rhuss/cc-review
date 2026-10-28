"""Shared PR assessment and reviewer lifecycle boundary tests."""
import copy
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "review/core/scripts"
sys.path.insert(0, str(SCRIPTS))


def thread(tid="T1"):
    root = {"id": "C" + tid, "databaseId": 101, "author": {"login": "me"},
            "body": "Unsafe access.\n_Source: correctness agent_", "updatedAt": "2026-10-20T00:00:00Z",
            "originalCommit": {"oid": "old"}}
    reply = {"id": "R" + tid, "databaseId": 102, "author": {"login": "alice"},
             "body": "Fixed now", "updatedAt": "2026-10-21T00:00:00Z"}
    return {"id": tid, "isResolved": False, "root": root, "comments": {
        "nodes": [root, reply], "totalCount": 2,
        "pageInfo": {"hasNextPage": False, "hasPreviousPage": False}}}


IDENTITY = {"host": "github.com", "repository": "acme/widget", "user": "me", "pr": 7}


def write_record(path, tid):
    os.environ["CC_REVIEW_REVIEWER_STATE_FILE"] = path
    module = importlib.import_module("reviewer_activity")
    module.record_activity("github.com", "acme/widget", "me", 7,
                           module.fingerprint(thread(tid), "head", "me"),
                           {"status": "still-present", "completed": True})


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.a = importlib.import_module("reviewer_activity")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state" / "cache.json"
        patcher = mock.patch.dict(os.environ, CC_REVIEW_REVIEWER_STATE_FILE=str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_read_does_not_create_any_path(self):
        self.assertEqual(({}, []), self.a.load_activity("github.com", "acme/widget", "me"))
        self.assertFalse(self.path.parent.exists())

    def test_dot_repository_name_is_safe_and_valid(self):
        for name in (".github", "_tool", "-tool"):
            self.assertEqual(({}, []), self.a.load_activity("github.com", "acme/" + name, "me"))
        self.assertFalse(self.path.parent.exists())

    def test_fingerprint_requires_owned_complete_exact_evidence(self):
        t = thread()
        activity = self.a.fingerprint(t, "head", "me")
        self.assertEqual("T1", activity["thread_id"])
        self.assertEqual("CT1", activity["root_comment_id"])
        for field, value in (("id", "OTHER"), ("body", "Edited"), ("updatedAt", "later")):
            changed = copy.deepcopy(t)
            changed["comments"]["nodes"][1][field] = value
            self.assertNotEqual(activity, self.a.fingerprint(changed, "head", "me"))
        self.assertNotEqual(activity, self.a.fingerprint(t, "moved", "me"))
        for change in (lambda x: x["root"].update(author={"login": "other"}),
                       lambda x: x["root"].update(body="manual"),
                       lambda x: x["comments"]["pageInfo"].update(hasPreviousPage=True)):
            changed = copy.deepcopy(t)
            change(changed)
            self.assertIsNone(self.a.fingerprint(changed, "head", "me"))

    def test_provenance_ignores_fenced_examples(self):
        changed = thread()
        changed["root"]["body"] = "Manual note with example:\n```markdown\n_Source: correctness agent_\n```"
        self.assertFalse(self.a.owned_root(changed["root"], "me"))
        self.assertIsNone(self.a.fingerprint(changed, "head", "me"))
        changed["root"]["body"] = "Manual note"
        changed["root"]["pullRequestReview"] = {
            "author": {"login": "me"}, "body": "~~~markdown\n<!-- cc-review:run-id:example -->\n~~~"}
        self.assertFalse(self.a.owned_root(changed["root"], "me"))
        self.assertIsNone(self.a.fingerprint(changed, "head", "me"))

    def test_marker_is_bounded_unquoted_and_owned(self):
        t = thread()
        activity = self.a.fingerprint(t, "head", "me")
        marker = self.a.activity_marker(IDENTITY, activity, "")
        self.assertEqual(activity, self.a.parse_activity_marker(marker)["activity"])
        for body in ("> " + marker, "`" + marker + "`", marker + "\n" + marker,
                     "<!-- cc-review-activity:v1 {} -->", "```\n" + marker + "\n```"):
            self.assertIsNone(self.a.parse_activity_marker(body))
        for actor, unchanged in (("me", True), ("intruder", False)):
            changed = copy.deepcopy(t)
            changed["comments"]["nodes"].append({"id": "handling", "body": marker,
                "author": {"login": actor}, "updatedAt": "later"})
            changed["comments"]["totalCount"] += 1
            self.assertEqual(unchanged, activity == self.a.fingerprint(changed, "head", "me"))

    def test_real_marker_after_code_block_is_not_a_quoted_example(self):
        t = thread()
        current = self.a.fingerprint(t, "head", "me")
        body_text = "Fix confirmed:\n```python\nassert valid\n```\n\n<!-- cc-review-triage -->"
        marker = self.a.activity_marker(IDENTITY, current, body_text)
        body = "Fix confirmed:\n```python\nassert valid\n```\n\n<!-- cc-review-triage -->\n" + marker
        self.assertIsNotNone(self.a.parse_activity_marker(body))
        for quoted in ("```html\n" + marker + "\n```", "> " + marker,
                       "~~~html\n" + marker + "\n~~~", "    " + marker):
            self.assertIsNone(self.a.parse_activity_marker(quoted))
        t["comments"]["nodes"].append({"id": "reply", "author": {"login": "me"},
                                         "body": body, "updatedAt": "later"})
        t["comments"]["totalCount"] += 1
        self.assertEqual(current, self.a.fingerprint(t, "head", "me"))

    def test_freshness_guard_rejects_each_changed_boundary(self):
        t = thread()
        activity = self.a.fingerprint(t, "head", "me")
        pr = {"state": "OPEN", "head_oid": "head", "author": "alice"}
        self.assertTrue(self.a.check_activity(IDENTITY, activity, pr, t)["allowed"])
        for changed in (dict(pr, state="CLOSED"), dict(pr, head_oid="new"), dict(pr, author="me")):
            self.assertFalse(self.a.check_activity(IDENTITY, activity, changed, t)["allowed"])
        for change in (lambda x: x.update(id="other"), lambda x: x.update(isResolved=True),
                       lambda x: x["root"].update(id="replacement"),
                       lambda x: x["comments"]["nodes"][1].update(body="another reply")):
            changed = copy.deepcopy(t)
            change(changed)
            self.assertFalse(self.a.check_activity(IDENTITY, activity, pr, changed)["allowed"])

    def test_single_pr_reviewer_check_leaves_isolated_checkout_untouched(self):
        checkout = Path(self.tmp.name) / "fixture-checkout"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        subprocess.run(["git", "-C", str(checkout), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(checkout), "config", "user.name", "Test"], check=True)
        tracked = checkout / "README.md"
        tracked.write_text("PR head\n")
        subprocess.run(["git", "-C", str(checkout), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(checkout), "commit", "-q", "-m", "fixture"], check=True)

        def snapshot():
            head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True)
            index = subprocess.check_output(["git", "-C", str(checkout), "ls-files", "--stage"], text=True)
            status = subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"], text=True)
            return head, index, status, tracked.read_bytes()

        before = snapshot()
        activity = self.a.fingerprint(thread(), "head", "me", IDENTITY)
        envelope = {"identity": IDENTITY, "expected": activity,
                    "current_pr": {"state": "OPEN", "head_oid": "head", "author": "alice"},
                    "thread": thread()}
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "reviewer_activity.py"), "check"],
            cwd=checkout, input=json.dumps(envelope), text=True, capture_output=True, timeout=5,
            env=dict(os.environ, CC_REVIEW_REVIEWER_STATE_FILE=str(self.path)))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["allowed"])
        self.assertEqual(before, snapshot())
        self.assertFalse(self.path.exists())

    def test_atomic_no_post_records_and_pending_outcomes(self):
        activity = self.a.fingerprint(thread(), "head", "me", IDENTITY)
        self.a.record_activity("github.com", "acme/widget", "me", 7, activity,
                               {"status": "still-present", "completed": True})
        records, warnings = self.a.load_activity("github.com", "acme/widget", "me")
        self.assertFalse(warnings)
        self.assertEqual("still-present", records["7/T1"]["outcome"]["status"])
        before = self.path.read_bytes()
        for outcome in ({"status": "unclear", "completed": False},
                        {"status": "confirmed-fixed", "completed": False}):
            self.a.record_activity("github.com", "acme/widget", "me", 7, activity, outcome)
            self.assertEqual(before, self.path.read_bytes())
        with mock.patch.object(self.a.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.a.record_activity("github.com", "acme/widget", "me", 7,
                    self.a.fingerprint(thread("T2"), "head", "me"),
                    {"status": "still-present", "completed": True})
        self.assertEqual(before, self.path.read_bytes())

    def test_record_rejects_thread_ids_that_break_cache_keys(self):
        activity = self.a.fingerprint(thread("nested/thread"), "head", "me")
        with self.assertRaisesRegex(ValueError, "thread_id cannot contain"):
            self.a.record_activity("github.com", "acme/widget", "me", 7, activity,
                                   {"status": "still-present", "completed": True})
        self.assertFalse(self.path.exists())

    def test_malformed_wrong_identity_and_unsafe_paths(self):
        self.path.parent.mkdir()
        for content in ("bad json", "null", json.dumps({"schema_version": 1, "host": "evil"})):
            self.path.write_text(content)
            records, warnings = self.a.load_activity("github.com", "acme/widget", "me")
            self.assertEqual({}, records)
            self.assertTrue(warnings)
        for host, repo, user in (("../host", "a/b", "me"), ("github.com", "a/..", "me"),
                                 ("github.com", "a/b", "../user")):
            with self.assertRaises(ValueError):
                self.a.load_activity(host, repo, user)

    def test_concurrent_writers_preserve_unrelated_threads(self):
        ctx = multiprocessing.get_context("spawn")
        jobs = [ctx.Process(target=write_record, args=(str(self.path), tid)) for tid in ("T1", "T2")]
        for job in jobs:
            job.start()
        for job in jobs:
            job.join(10)
            self.assertEqual(0, job.exitcode)
        records, warnings = self.a.load_activity("github.com", "acme/widget", "me")
        self.assertFalse(warnings)
        self.assertEqual({"7/T1", "7/T2"}, set(records))

    def test_invalid_cached_outcome_is_incomplete_not_handled(self):
        current = self.a.fingerprint(thread(), "head", "me")
        self.a.record_activity("github.com", "acme/widget", "me", 7, current,
                               {"status": "still-present", "completed": True})
        valid = json.loads(self.path.read_text())
        for outcome in ({"completed": True}, {"status": "invented", "completed": True},
                        {"status": "still-present", "completed": "yes"}):
            changed = copy.deepcopy(valid)
            changed["records"]["7/T1"]["outcome"] = outcome
            self.path.write_text(json.dumps(changed))
            records, warnings = self.a.load_activity("github.com", "acme/widget", "me")
            self.assertEqual({}, records)
            self.assertTrue(warnings)


def pr(number=7, author="alice"):
    return {"host": "github.com", "repository": "acme/widget", "user": "me", "number": number,
            "title": "Change", "author": author, "state": "OPEN", "is_draft": False,
            "head_oid": "head", "updated_at": "2026-10-21", "reasons": [], "reviews": [],
            "threads": [], "coverage": {"reviews": True, "threads": True}, "seed": {"number": number}}


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.p = importlib.import_module("pr_actions")
        self.a = importlib.import_module("reviewer_activity")

    def assess(self, value, handled=None, **kw):
        return self.p.assess_pr(value, handled or {}, **kw)

    def test_independent_actions_drafts_and_owned_thread_activity(self):
        value = pr()
        value.update(reasons=["review_requested"], threads=[thread()])
        result = self.assess(value)
        self.assertTrue(result["review"]["eligible"])
        self.assertTrue(result["triage"]["eligible"])
        self.assertEqual("reviewer", result["triage"]["role"])
        value["is_draft"] = True
        result = self.assess(value)
        self.assertEqual("draft", result["review"]["exclusion"])
        self.assertTrue(result["triage"]["eligible"])
        value["author"] = "me"
        self.assertEqual("author", self.assess(value)["triage"]["role"])

    def test_review_marker_policy_and_conservative_changed_head(self):
        value = pr()
        value["reviews"] = [{"author": {"login": "me"}, "body": "<!-- cc-review:run-id:r -->",
                             "commit": {"oid": "old"}}]
        result = self.assess(value)["review"]
        self.assertTrue(result["eligible"])
        self.assertTrue(result["uncertain"])
        value["contribution"] = {"reliable": True, "unchanged": True}
        self.assertFalse(self.assess(value)["review"]["eligible"])
        value["reasons"] = ["review_requested"]
        self.assertTrue(self.assess(value)["review"]["eligible"])
        value["reviews"][0]["commit"]["oid"] = "head"
        self.assertEqual("reviewed-at-head", self.assess(value)["review"]["exclusion"])
        value["reviews"][0]["author"]["login"] = "alice"
        self.assertTrue(self.assess(value)["review"]["eligible"])
        triage_value = pr()
        triage_value.update(reviews=[{"author":{"login":"me"},"body":"<!-- cc-review:run-id:r -->",
                                      "commit":{"oid":"head"}}], threads=[thread()])
        self.assertTrue(self.assess(triage_value)["triage"]["eligible"],
                        "a review-level marker alone does not mark reviewer thread activity handled")

    def test_fresh_code_and_replies_reactivate_only_owned_findings(self):
        value = pr()
        t = thread()
        t["comments"]["nodes"] = [t["root"]]
        t["comments"]["totalCount"] = 1
        value["threads"] = [t]
        self.assertTrue(self.assess(value)["triage"]["eligible"])
        activity = self.a.fingerprint(t, "head", "me")
        records = {"7/T1": dict(activity, outcome={"status": "still-present", "completed": True})}
        self.assertFalse(self.assess(value, records)["triage"]["eligible"])
        value["head_oid"] = "later"
        self.assertTrue(self.assess(value, records)["triage"]["eligible"])
        value["head_oid"] = "head"
        t["comments"] = thread()["comments"]
        self.assertTrue(self.assess(value, records)["triage"]["eligible"])
        for change in (lambda t: t.update(isResolved=True),
                       lambda t: t["root"].update(author={"login": "other"}),
                       lambda t: t["root"].update(body="Manual comment")):
            changed = copy.deepcopy(value)
            change(changed["threads"][0])
            self.assertFalse(self.assess(changed)["triage"]["eligible"])

    def test_triage_then_review_preserves_independent_action_and_reactivates_new_activity(self):
        value = pr()
        value.update(reasons=["review_requested"], threads=[thread()])
        initial = self.assess(value)
        self.assertTrue(initial["review"]["eligible"])
        self.assertTrue(initial["triage"]["eligible"])
        activity = self.a.fingerprint(value["threads"][0], value["head_oid"], "me", IDENTITY)
        handled = {"7/T1": dict(activity, outcome={"status":"still-present", "completed":True})}
        after_triage = self.assess(value, handled)
        self.assertTrue(after_triage["review"]["eligible"], "triage does not advance the review baseline")
        self.assertFalse(after_triage["triage"]["eligible"])
        value["reviews"] = [{"author":{"login":"me"},"body":"<!-- cc-review:run-id:run -->",
                             "commit":{"oid":"head"}}]
        self.assertFalse(self.assess(value, handled)["review"]["eligible"], "the full review marker advances only review's own baseline")
        self.assertFalse(self.assess(value, handled)["triage"]["eligible"],
                         "a review marker does not clear a different handled-activity record")
        value["threads"][0]["comments"]["nodes"][1]["body"] = "New reply after review"
        self.assertTrue(self.assess(value, handled)["triage"]["eligible"],
                        "new thread activity reactivates triage")

    def test_known_author_feedback_preserves_incomplete_coverage(self):
        value = pr(author="me")
        value.update(threads=[thread()], coverage={"reviews": True, "threads": False})
        result = self.p.select_prs([value], {}, "triage", 10)
        self.assertEqual([7], [p["number"] for p in result["selected"]])
        self.assertFalse(result["selected"][0]["assessment"]["triage"]["complete"])
        self.assertIn("PR #7", " ".join(result["warnings"]))
        self.assertEqual("PR #7: Unresolved feedback on your PR; thread coverage is incomplete", result["warnings"][0])

    def test_unvalidated_handled_outcome_does_not_suppress_activity(self):
        value = pr()
        value["threads"] = [thread()]
        current = self.a.fingerprint(thread(), "head", "me")
        self.assertTrue(self.assess(value, {"7/T1": dict(current, outcome={"completed": True})})["triage"]["eligible"])

    def test_incomplete_triage_keeps_explicit_review_and_scope_exclusions(self):
        value = pr()
        value.update(reasons=["review_requested"], coverage={"reviews": True, "threads": False})
        result = self.assess(value)
        self.assertTrue(result["review"]["eligible"])
        self.assertFalse(result["triage"]["complete"])
        self.assertFalse(result["triage"]["eligible"])
        for state in ("CLOSED", "MERGED"):
            result = self.assess(dict(value, state=state))
            self.assertEqual("closed", result["review"]["exclusion"])
            self.assertFalse(result["triage"]["eligible"])

    def test_explicit_modes_and_deterministic_limit(self):
        values = [pr(9), pr(2), pr(5)]
        self.assertFalse(self.assess(values[0])["review"]["eligible"])
        result = self.p.select_prs(values, {}, "review", 2, review_mode="all-open")
        self.assertEqual([2, 5], [p["number"] for p in result["selected"]])
        self.assertEqual("over-limit", result["excluded"][0]["reason"])
        self.assertTrue(self.assess(pr(), review_mode="search")["review"]["eligible"])
        with self.assertRaises(ValueError):
            self.p.select_prs(values, {}, "review", 0)


class NormalizationCLITests(unittest.TestCase):
    def setUp(self):
        self.p = importlib.import_module("pr_actions")
        self.a = importlib.import_module("reviewer_activity")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "missing/cache.json")

    def cli(self, script, args, value=None, raw=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / script), *args],
            input=raw if raw is not None else json.dumps(value), text=True, capture_output=True,
            env=dict(os.environ, CC_REVIEW_REVIEWER_STATE_FILE=self.path), timeout=5)

    def args(self, op="assess", source="canonical"):
        return [op, "--source", source, "--repo", "acme/widget", "--user", "me",
                "--host", "github.com", "--review-mode", "default"]

    def test_equal_raw_inbox_bulk_assessments_and_missing_fields(self):
        raw = {"number": 7, "title": "Change", "author": {"login": "alice"}, "state": "OPEN",
               "isDraft": False, "headRefOid": "head", "updatedAt": "2026-10-21", "reviews": [],
               "reviewThreads": {"nodes": [thread()], "totalCount": 1,
                                 "pageInfo": {"hasNextPage": False, "hasPreviousPage": False}},
               "reasons": ["review_requested"]}
        inbox_raw = dict(raw, reviews={"nodes": [], "totalCount": 0,
                         "pageInfo": {"hasNextPage": False, "hasPreviousPage": False}})
        inbox = {"number": 7, "reasons": raw["reasons"], "detail": inbox_raw}
        left = self.p.normalize_pr(inbox, "inbox", "acme/widget", "me")
        right = self.p.normalize_pr(raw, "bulk", "acme/widget", "me")
        self.assertEqual(self.p.assess_pr(left, {}), self.p.assess_pr(right, {}))
        self.assertTrue(self.p.assess_pr(left, {})["triage"]["eligible"])
        alias = copy.deepcopy(raw)
        alias["reviewThreads"]["nodes"][0]["rootComment"] = {"nodes": [thread()["root"]]}
        del alias["reviewThreads"]["nodes"][0]["root"]
        self.assertTrue(self.p.assess_pr(self.p.normalize_pr(alias, "bulk", "acme/widget", "me"), {})["triage"]["eligible"])
        for key in ("reviews", "reviewThreads", "headRefOid", "author"):
            missing = dict(raw, **{key: None})
            result = self.p.assess_pr(self.p.normalize_pr(missing, "bulk", "acme/widget", "me"), {})
            self.assertFalse(result["triage" if key in ("reviewThreads", "author") else "review"]["complete"])
        self.assertFalse(Path(self.path).parent.exists())

    def test_bot_only_activity_is_not_a_human_follow_up(self):
        value = pr()
        value["head_oid"] = "old"
        value["threads"] = [thread()]
        reply = value["threads"][0]["comments"]["nodes"][1]
        reply["author"] = {"login": "helper[bot]", "__typename": "Bot"}
        self.assertFalse(self.p.assess_pr(value, {})["triage"]["eligible"])
        reply["author"] = None
        result = self.p.assess_pr(value, {})["triage"]
        self.assertFalse(result["eligible"])
        self.assertFalse(result["complete"])
        value["head_oid"] = "changed-code"
        self.assertTrue(self.p.assess_pr(value, {})["triage"]["eligible"])

    def test_action_cli_envelopes_and_actionable_invalid_input(self):
        value = json.loads((Path(__file__).parent / "fixtures/bulk/pr-actions.json").read_text())[0]
        result = self.cli("pr_actions.py", self.args(), [value])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["assessments"][0]["review"]["eligible"])
        result = self.cli("pr_actions.py", self.args("select") + ["--action", "review", "--limit", "1"], [value])
        self.assertEqual([7], [v["number"] for v in json.loads(result.stdout)["selected"]])
        for raw in ("broken", "null", "{}", "[null]", '[{"number":null}]'):
            result = self.cli("pr_actions.py", self.args(), raw=raw)
            self.assertEqual(2, result.returncode, (raw, result.stdout, result.stderr))
            self.assertTrue(result.stderr)
            self.assertEqual("", result.stdout)
        for malformed in (dict(value, reviews=[None]), dict(value, threads=[None]),
                          dict(value, author=123), dict(value, head_oid=123),
                          dict(value, coverage={"reviews": "yes"}), dict(value, is_draft="false"),
                          dict(value, reviews=[dict(value["reviews"][0], commit="bad")]),
                          dict(value, threads=[dict(value["threads"][0], coverage=None)])):
            result = self.cli("pr_actions.py", self.args(), [malformed])
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual("", result.stdout)
        result = self.cli("pr_actions.py", self.args("select") + ["--action", "triage", "--limit", "0"], [])
        self.assertEqual(2, result.returncode)
        self.assertFalse(Path(self.path).parent.exists())

    def test_activity_cli_operations_and_exit_contract(self):
        result = self.cli("reviewer_activity.py", ["load"], {"identity": IDENTITY})
        self.assertEqual({"records": {}, "complete": True, "warnings": []}, json.loads(result.stdout))
        result = self.cli("reviewer_activity.py", ["fingerprint"],
                          {"identity": IDENTITY, "head_oid": "head", "thread": thread()})
        self.assertEqual(0, result.returncode, result.stderr)
        activity = json.loads(result.stdout)["activity"]
        self.assertTrue(json.loads(result.stdout)["complete"])
        result = self.cli("reviewer_activity.py", ["check"], {"identity": IDENTITY, "expected": activity,
            "current_pr": {"state": "OPEN", "head_oid": "head", "author": "alice"}, "thread": thread()})
        self.assertTrue(json.loads(result.stdout)["allowed"])
        result = self.cli("reviewer_activity.py", ["record"], {"identity": IDENTITY, "activity": activity,
            "outcome": {"status": "still-present", "completed": True}, "reply_id": None, "resolved": False})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["recorded"])
        result = self.cli("reviewer_activity.py", ["load"], {"identity": IDENTITY})
        self.assertIn("7/T1", json.loads(result.stdout)["records"])
        for value in (None, {}, {"identity": dict(IDENTITY, pr=None)}, {"identity": dict(IDENTITY, repository="../repo")}):
            result = self.cli("reviewer_activity.py", ["load"], value)
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)
        result = self.cli("reviewer_activity.py", ["unknown"], {})
        self.assertEqual(2, result.returncode)
        Path(self.path).write_text("malformed")
        result = self.cli("reviewer_activity.py", ["load"], {"identity": IDENTITY})
        self.assertFalse(json.loads(result.stdout)["complete"])
        result = self.cli("reviewer_activity.py", ["record"], {"identity": IDENTITY, "activity": activity,
            "outcome": {"status": "still-present", "completed": True}, "reply_id": None, "resolved": False})
        self.assertEqual(1, result.returncode)
        self.assertEqual("malformed", Path(self.path).read_text())

    def test_exact_activity_marker_recovers_only_matching_authenticated_reply(self):
        activity = self.a.fingerprint(thread(), "head", "me")
        conversation = thread()
        marker = self.a.activity_marker(IDENTITY, activity, "Verified.")
        reply = {"id": "reply-node", "databaseId": 777, "author": {"login": "me"},
                 "body": "Verified.", "updatedAt": "2026-10-22T00:00:00Z"}
        reply["body"] += "\n\n" + marker
        conversation["comments"]["nodes"].append(reply)
        conversation["comments"]["totalCount"] = 3
        self.assertEqual(activity, self.a.fingerprint(conversation, "head", "me"))
        self.assertEqual(777, self.a.matching_activity_reply(conversation, IDENTITY, activity))
        self.assertIsNone(self.a.matching_activity_reply(conversation,
            dict(IDENTITY, user="other"), activity))
        reply["body"] = "Correction: NOT fixed; keep open.\n\n" + marker
        self.assertNotEqual(activity, self.a.fingerprint(conversation, "head", "me", IDENTITY))
        checked = self.a.check_activity(IDENTITY, activity,
            {"state":"OPEN", "head_oid":"head", "author":"alice"}, conversation)
        self.assertFalse(checked["allowed"])
        reply["body"] = "Verified.\n\n" + marker
        reply["body"] += "\n\nCorrection: this is not fixed."
        self.assertIsNone(self.a.matching_activity_reply(conversation, IDENTITY, activity))
        self.assertFalse(self.a.check_activity(IDENTITY, activity,
            {"state":"OPEN", "head_oid":"head", "author":"alice"}, conversation)["allowed"])
        reply["body"] = "Verified.\n\n" + marker
        reply["author"] = {"login": "other"}
        self.assertIsNone(self.a.matching_activity_reply(conversation, IDENTITY, activity))
        reply["author"] = {"login": "me"}
        wrong_activity = dict(activity, head_oid="different-head")
        wrong_activity["activity_key"] = self.a._hash(["me", {k: v for k, v in wrong_activity.items() if k != "activity_key"}])
        reply["body"] = "Verified.\n\n" + self.a.activity_marker(IDENTITY, wrong_activity, "Verified.")
        conversation["comments"]["totalCount"] = 3
        self.assertNotEqual(activity, self.a.fingerprint(conversation, "head", "me", IDENTITY))


if __name__ == "__main__":
    unittest.main()
