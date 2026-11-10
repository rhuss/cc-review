"""The triage preview shows every text bulk triage would post, in full."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "review/core/scripts"))
import triage_preview as tp

IDENTITY = dict(host="github.com", repository="acme/widget", user="me", pr=36)


def author_plan(commit=None):
    return dict(
        pr=36, triage_role="author", activity_identity=IDENTITY, prepared_commit=commit,
        replies=[
            dict(comment_id=4398981895, thread_id="T1", author="greptile-apps[bot]", path="a.go", line=12,
                 body="Fixed in the push: the closure now checks the ground pane.\n\n<!-- cc-review-triage -->", action="accepted", resolve=True),
            dict(comment_id=4398981896, thread_id="T2", author="greptile-apps[bot]", path="b.go", line=None,
                 body="Not changing this: the CSI parser is shared with the renderer.", action="rejected", resolve=False),
            dict(comment_id=4398981897, thread_id="T3", author="coderabbitai[bot]", path="c.go", line=3,
                 body="", action="deferred", resolve=False),
        ],
        cc_review_threads=[],
        stale_resolutions=["T9"],
        human=[
            dict(comment_id=789, thread_id="H1", path="b.sh", line=3, author="carol",
                 text="Why not a loop?", draft="Because the order matters.", decision="approve"),
            dict(comment_id=790, thread_id="H2", path="c.sh", line=9, author="dave",
                 text="Rename this", draft="Done.", body="Renamed to paneGround.", decision="edit"),
            dict(comment_id=791, thread_id="H3", path="d.sh", line=1, author="erin",
                 text="Nit", draft="Ok.", decision="skip"),
        ],
        resolution_summary=None)


def reviewer_plan():
    def item(n, status, body, resolve, key):
        return dict(comment_id=500 + n, thread_id="R" + str(n), author="alice", path="x.py", line=n,
                    activity=dict(activity_key=key), viewer_can_resolve=resolve, resolve=resolve, body=body,
                    outcome=dict(status=status, completed=True))
    return dict(
        pr=40, triage_role="reviewer", activity_identity=dict(IDENTITY, pr=40), prepared_commit=None,
        replies=[], human=[], stale_resolutions=[],
        cc_review_threads=[
            item(1, "confirmed-fixed", "", False, "a" * 64),
            item(2, "confirmed-fixed", "Verified: the guard is in place.", True, "b" * 64),
            item(3, "still-present", "", False, "c" * 64),
            dict(item(4, "unclear", "", False, "d" * 64), outcome=dict(status="unclear", completed=False)),
        ],
        resolution_summary=dict(body="Verified reviewer findings at `abc`.\n\n- [Thread 501](u): fix confirmed.",
                                activity_keys=["a" * 64], summary_key="k"))


class AuthorPreview(unittest.TestCase):
    def test_every_posted_text_is_shown_in_full(self):
        text = tp.render(author_plan())
        self.assertIn("Fixed in the push: the closure now checks the ground pane.", text)
        self.assertIn("Not changing this: the CSI parser is shared with the renderer.", text)
        self.assertIn("https://github.com/acme/widget/pull/36#discussion_r4398981895", text)
        self.assertIn("`a.go:12` · greptile-apps[bot] · accepted · resolve yes", text)
        self.assertIn("`b.go` · greptile-apps[bot] · rejected · resolve no", text)
        self.assertIn("Because the order matters.", text)
        self.assertIn("Renamed to paneGround.", text)
        self.assertIn("Why not a loop?", text)
        self.assertNotIn("Ok.", text)
        self.assertIn("- Human comments: 1 approved, 1 edited, 1 skipped, 0 undecided", text)
        self.assertIn("- `T9`", text)
        self.assertIn("`c.go:3` (coderabbitai[bot]): no reply text", text)
        self.assertIn("- Push: none", text)
        self.assertNotIn("cc-review-triage", text)

    def test_local_unpushed_holds_accepted_replies(self):
        text = tp.render(author_plan("71e5065aaaa"), flags=["local-unpushed"])
        self.assertIn("commit `71e5065` is NOT pushed", text)
        self.assertIn("`a.go:12` (greptile-apps[bot]): fixes are not pushed", text)
        self.assertNotIn("### 1. `a.go:12`", text)

    def test_local_unpushed_without_a_prepared_commit_posts_accepted_replies(self):
        # bulk-apply.sh only holds accepted replies when it has a commit to
        # leave unpushed; the preview must not promise a hold apply will not do
        text = tp.render(author_plan(), flags=["local-unpushed"])
        self.assertIn("### 1. `a.go:12`", text)
        self.assertNotIn("fixes are not pushed", text)

    def test_replies_posted_in_an_earlier_attempt_are_not_shown_as_new(self):
        # bulk-apply.sh neither posts nor updates a reply recorded by a
        # partial apply; an edit to it would never reach GitHub
        text = tp.render(author_plan(), recorded={"4398981895": 1234})
        self.assertNotIn("### 1. `a.go:12`", text)
        self.assertIn("## Already posted in an earlier attempt", text)
        self.assertIn("`a.go:12` (greptile-apps[bot]): already posted as "
                      "[reply](https://github.com/acme/widget/pull/36#discussion_r1234)", text)
        self.assertIn("- Already posted in an earlier attempt: 1", text)
        self.assertIn("`b.go` · greptile-apps[bot] · rejected · resolve no", text)

    def test_commit_message_and_stat_from_worktree(self):
        with tempfile.TemporaryDirectory() as d:
            run = lambda *a: subprocess.run(["git", "-C", d] + list(a), check=True, capture_output=True, text=True)
            run("init", "-q")
            run("config", "user.email", "t@example.com")
            run("config", "user.name", "T")
            Path(d, "f.txt").write_text("x\n")
            run("add", "f.txt")
            run("commit", "-q", "-m", "fix: guard the ground pane\n\nCloses three bot threads.")
            sha = run("rev-parse", "HEAD").stdout.strip()
            text = tp.render(author_plan(sha), worktree=d)
        self.assertIn("- Push: commit `{}`".format(sha[:7]), text)
        self.assertIn("fix: guard the ground pane", text)
        self.assertIn("Closes three bot threads.", text)
        self.assertIn("f.txt", text)

    def test_missing_worktree_is_said_not_hidden(self):
        text = tp.render(author_plan("71e5065aaaa"), worktree="/nonexistent/wt")
        self.assertIn("commit details unavailable", text)


class ReviewerPreview(unittest.TestCase):
    def test_summary_replies_and_records(self):
        text = tp.render(reviewer_plan())
        self.assertIn("- Role: reviewer", text)
        self.assertIn("Verified reviewer findings at `abc`.", text)
        self.assertIn("1, covering 1 threads (the PR author must resolve them)", text)
        self.assertIn("Verified: the guard is in place.", text)
        self.assertIn("- Thread replies: 1 (1 also resolve the thread)", text)
        self.assertIn("- Outcomes recorded without posting: 1", text)
        self.assertIn("outcome unclear: nothing is posted", text)
        self.assertNotIn("### 2.", text)

    def test_trusted_role_overrides_the_plan(self):
        self.assertIn("- Role: reviewer", tp.render(dict(author_plan(), triage_role="author"), role="reviewer"))


class Fingerprint(unittest.TestCase):
    def test_stable_and_sensitive_to_text(self):
        plan = author_plan()
        self.assertEqual(tp.fingerprint(plan), tp.fingerprint(json.loads(json.dumps(plan))))
        changed = author_plan()
        changed["replies"][1]["body"] += " Edited."
        self.assertNotEqual(tp.fingerprint(plan), tp.fingerprint(changed))

    def test_cli_writes_preview_next_to_plan(self):
        with tempfile.TemporaryDirectory() as d:
            plan = Path(d, "triage-plan.json")
            plan.write_text(json.dumps(author_plan()))
            out = subprocess.run([sys.executable, "-B", tp.__file__, "render", "--plan", str(plan)],
                                 check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(str(Path(d, "triage-preview.md")), out)
            self.assertIn("# Triage preview: PR #36", Path(out).read_text())
            fp = subprocess.run([sys.executable, "-B", tp.__file__, "fingerprint", "--plan", str(plan)],
                                check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(tp.fingerprint(author_plan()), fp)


if __name__ == "__main__":
    unittest.main()
