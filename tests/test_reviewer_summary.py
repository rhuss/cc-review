"""Grouped reviewer notifications preserve exact activity and publication evidence."""
import copy
import importlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "review/core/scripts"))
from test_pr_actions import IDENTITY, thread
import reviewer_activity as activity


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.s = importlib.import_module("reviewer_summary")
        self.threads = [thread("T" + str(i)) for i in range(64)]
        self.plan = dict(triage_role="reviewer", activity_identity=IDENTITY,
                         expected_head="head", cc_review_threads=[])
        for index, t in enumerate(self.threads):
            t["comments"]["nodes"][0]["databaseId"] = 101 + index
            root = t["comments"]["nodes"][0]
            self.plan["cc_review_threads"].append(dict(
                thread_id=t["id"], comment_id=root["databaseId"],
                activity=activity.fingerprint(t, "head", "me", IDENTITY),
                viewer_can_resolve=False, resolve=True, body="Verified fixed.",
                outcome=dict(status="confirmed-fixed", completed=True)))
        self.pr = dict(state="OPEN", head_oid="head", author="alice")

    def test_prepare_64_threads_one_summary_and_no_individual_writes(self):
        plan = self.s.prepare(self.plan)
        summary = plan["resolution_summary"]
        self.assertEqual(64, len(summary["activity_keys"]))
        self.assertEqual(64, summary["body"].count("#discussion_r"))
        self.assertTrue(all(not i["resolve"] and i["body"] == "" for i in plan["cc_review_threads"]))
        self.assertEqual(plan, self.s.prepare(plan))

    def test_mixed_permission_and_pending_work_are_not_summarized(self):
        self.plan["cc_review_threads"][0]["viewer_can_resolve"] = True
        self.plan["cc_review_threads"][1]["outcome"] = dict(status="still-present", completed=True)
        self.plan["cc_review_threads"][2]["outcome"] = dict(status="accepted-explanation", completed=True)
        self.plan["cc_review_threads"][3]["outcome"] = dict(status="accepted-explanation", completed=True, approved=True)
        plan = self.s.prepare(self.plan)
        keys = plan["resolution_summary"]["activity_keys"]
        self.assertEqual(61, len(keys))
        self.assertTrue(plan["cc_review_threads"][0]["resolve"])
        for i in (0, 1, 2):
            self.assertNotIn(plan["cc_review_threads"][i]["activity"]["activity_key"], keys)

    def test_unknown_permission_uses_summary(self):
        del self.plan["cc_review_threads"][0]["viewer_can_resolve"]
        self.assertEqual(64, len(self.s.prepare(self.plan)["resolution_summary"]["activity_keys"]))

    def test_group_requires_fresh_exact_complete_activities(self):
        plan = self.s.prepare(self.plan)
        result = self.s.check(plan, self.pr, self.threads, [])
        self.assertIsNone(result["comment_id"])
        self.assertIn("cc-review-triage-summary:v1", result["body"])
        for change in (lambda ts: ts[0]["comments"]["nodes"][1].update(body="Changed"),
                       lambda ts: ts[0]["comments"]["pageInfo"].update(hasNextPage=True),
                       lambda ts: ts[0].update(isResolved=True)):
            changed = copy.deepcopy(self.threads)
            change(changed)
            with self.assertRaises(ValueError):
                self.s.check(plan, self.pr, changed, [])
        with self.assertRaises(ValueError):
            self.s.check(plan, dict(self.pr, head_oid="moved"), self.threads, [])

    def test_crash_recovery_requires_own_exact_body_and_marker(self):
        plan = self.s.prepare(self.plan)
        result = self.s.check(plan, self.pr, self.threads, [])
        comment = dict(databaseId=999, author=dict(login="me"), body=result["body"])
        self.assertEqual(999, self.s.check(plan, self.pr, self.threads, [comment])["comment_id"])
        copied = dict(comment, author=dict(login="other"))
        self.assertIsNone(self.s.check(plan, self.pr, self.threads, [copied])["comment_id"])
        with self.assertRaises(ValueError):
            self.s.check(plan, self.pr, self.threads, [dict(comment, body="Edited\n" + comment["body"])])
        changed = copy.deepcopy(self.threads)
        changed[0]["isResolved"] = True
        self.assertEqual(999, self.s.check(plan, self.pr, changed, [comment])["comment_id"])

    def test_summary_cannot_cover_wrong_outcomes_or_invented_activity(self):
        plan = self.s.prepare(self.plan)
        plan["cc_review_threads"][0]["outcome"]["status"] = "still-present"
        with self.assertRaises(ValueError):
            self.s.check(plan, self.pr, self.threads, [])
        plan = self.s.prepare(self.plan)
        plan["resolution_summary"]["activity_keys"].append("a" * 64)
        with self.assertRaises(ValueError):
            self.s.check(plan, self.pr, self.threads, [])


if __name__ == "__main__":
    unittest.main()
