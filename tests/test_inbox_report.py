"""Structure tests for the streamlined inbox report (US1).

The report itself is rendered by the prompt in review/core/commands/inbox.md, so
these tests assert two scriptable things:

1. the snapshot fixtures carry everything a correct report needs (one row per
   attention item with its five columns' worth of data, a situation, a
   recommendation source and an evidence link; PRs carry the shared
   assessment), and the empty variant discloses its coverage gap; and
2. inbox.md documents the report contract (the fixed table columns, the labeled
   "My take" recommendation, the evidence link, the brief lists, the empty-state
   string, and the read-only guarantee).

Mapped to SC-001, SC-005, FR-001..006 and the FR-005 empty/coverage edge case.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/inbox-snapshot.json"
FIXTURE_EMPTY = ROOT / "tests/fixtures/inbox-snapshot-empty.json"
INBOX_MD = ROOT / "review/core/commands/inbox.md"

# Report order (section 3/4): explicit requests before uncertain ones.
ATTENTION_TYPES = {"pr", "issue", "discussion"}


def load(path):
    return json.loads(path.read_text())


class SnapshotFixture(unittest.TestCase):
    def setUp(self):
        self.snap = load(FIXTURE)
        self.items = self.snap["items"]
        self.by_number = {i["number"]: i for i in self.items}

    def test_covers_all_attention_types(self):
        kinds = {i["type"] for i in self.items}
        for kind in ATTENTION_TYPES:
            self.assertIn(kind, kinds, f"fixture is missing a {kind} item")

    def test_every_item_has_reasons_and_link(self):
        # Each row needs identity+link and a reason it is relevant (FR-001).
        for item in self.items:
            self.assertTrue(item.get("reasons"), f"#{item['number']} has no reasons")
            self.assertTrue(item.get("url"), f"#{item['number']} has no link")
            self.assertIsNotNone(item.get("detail"), f"#{item['number']} has no detail")

    def test_detail_section_carries_its_own_evidence_link(self):
        # SC-005/FR-002: the detail section must carry an evidence link, not just
        # the row's top-level url. Checking item["detail"] specifically (rather
        # than the whole item, which the top-level url would always satisfy)
        # guards against a regression that drops detail-level evidence. Scoped to
        # items whose collected context has activity to discuss; an item with no
        # collected comments or threads (e.g. an assigned issue with no activity)
        # legitimately has no detail-level link.
        checked = 0
        for item in self.items:
            detail = item.get("detail") or {}
            comments = (detail.get("comments") or {}).get("nodes") or []
            threads = (detail.get("reviewThreads") or {}).get("nodes") or []
            if comments or threads:
                checked += 1
                self.assertIn(
                    "https://", json.dumps(detail),
                    f"#{item['number']} detail carries no evidence URL")
        self.assertGreater(
            checked, 0, "no fixture item exercises the detail evidence-link check")

    def test_prs_carry_shared_assessment(self):
        prs = [i for i in self.items if i["type"] == "pr"]
        self.assertTrue(prs, "fixture has no PR item")
        for pr in prs:
            a = pr.get("assessment")
            self.assertIsInstance(a, dict, f"PR #{pr['number']} has no assessment")
            for action in ("review", "triage"):
                self.assertIn(action, a, f"PR #{pr['number']} assessment lacks {action}")
                for key in ("eligible", "role", "reason", "complete", "exclusion"):
                    self.assertIn(key, a[action],
                                  f"PR #{pr['number']} {action} assessment lacks {key}")

    def test_fixture_exercises_all_three_report_groups(self):
        # Needs attention: an outstanding review request (109) and author
        # feedback (44). Waiting on others: an authored PR with no eligible
        # action whose own request is outstanding (50). No current action: an
        # assigned issue with no activity (88).
        self.assertTrue(self.by_number[109]["assessment"]["review"]["eligible"])
        self.assertTrue(self.by_number[44]["assessment"]["triage"]["eligible"])
        self.assertEqual("me", self.by_number[50]["author"])
        self.assertFalse(self.by_number[50]["assessment"]["review"]["eligible"])
        self.assertFalse(self.by_number[50]["assessment"]["triage"]["eligible"])
        self.assertIn(88, self.by_number)

    def test_certainty_values_are_known(self):
        for pr in (self.by_number[109], self.by_number[44]):
            for action in ("review", "triage"):
                self.assertIn(pr["assessment"][action]["uncertain"], (True, False))


class EmptyVariant(unittest.TestCase):
    def setUp(self):
        self.snap = load(FIXTURE_EMPTY)

    def test_no_attention_items(self):
        self.assertEqual([], self.snap["items"],
                         "the empty variant must have no attention items")

    def test_coverage_gap_is_disclosed(self):
        warnings = self.snap.get("warnings") or []
        self.assertTrue(warnings, "the empty variant must disclose a coverage warning")
        unavailable = [s for s in self.snap["sources"] if s["status"] == "unavailable"]
        self.assertTrue(unavailable,
                        "the empty variant must mark at least one source unavailable")


class ReportContract(unittest.TestCase):
    """inbox.md must document the fixed report structure (FR-001..006)."""

    @classmethod
    def setUpClass(cls):
        cls.md = INBOX_MD.read_text()

    def test_attention_table_has_the_five_columns(self):
        # The header row of the attention table, in order (FR-001, SC-001).
        self.assertRegex(
            self.md,
            r"\|\s*Item\s*\|\s*What\s*\|\s*Why you\s*\|\s*Certainty\s*\|\s*Next step\s*\|",
            "inbox.md does not document the five attention-table columns in order",
        )

    def test_certainty_values_documented(self):
        for token in ("`Explicit`", "`Inferred`", "`Uncertain`"):
            self.assertIn(token, self.md, f"certainty value {token} not documented")

    def test_detail_block_has_labeled_recommendation_and_evidence(self):
        # FR-002/FR-003: a per-item block with a labeled "My take" and a link.
        self.assertIn("### <Item> - <short title>", self.md)
        self.assertIn("My take:", self.md)
        self.assertIn("Evidence:", self.md)

    def test_my_take_is_an_opinion_not_an_obligation(self):
        self.assertRegex(self.md, r"My take[\s\S]{0,400}?(opinion|never an obligation)")

    def test_brief_lists_for_the_other_groups(self):
        self.assertIn("Waiting on others", self.md)
        self.assertIn("No current action", self.md)
        self.assertRegex(self.md, r"brief two-column lists")

    def test_empty_group_string(self):
        self.assertIn("None found in the inspected scope.", self.md)

    def test_coverage_account_kept_compressed(self):
        self.assertRegex(self.md, r"Coverage account")
        self.assertIn("scope.known_limits", self.md)
        self.assertIn("detail_bounds", self.md)

    def test_read_only_guarantee(self):
        # FR-006: producing the report performs no write.
        for phrase in (
            "no comment posted",
            "no thread resolved",
            "no branch pushed",
            "no review or triage agent launched",
            "no change to the working tree",
        ):
            self.assertIn(phrase, self.md, f"read-only guarantee missing: {phrase}")


class TourAndFanoutContract(unittest.TestCase):
    """inbox.md must document the guided-tour (US2) and fan-out (US3) contract.

    These are string-assertable like the US1 ReportContract above: the prompt
    pins the tour-offer gate, the five-item batch rule, the next-batch choice,
    the per-item fan-out offers, and the degradation handoff. Mapped to
    FR-007..019 and SC-006.
    """

    @classmethod
    def setUpClass(cls):
        cls.md = INBOX_MD.read_text()

    def test_tour_is_opt_in_after_report(self):
        # FR-007: an opt-in tour offered after the report; declining leaves it.
        self.assertRegex(self.md, r"Offer the Guided Tour \(opt-in\)")
        self.assertRegex(self.md, r"declines? the")

    def test_tour_offer_gated_on_nonempty_and_interactive(self):
        # FR-007: offered only when the attention group is non-empty AND the run
        # is interactive; otherwise end with the read-only report.
        self.assertIn('"Needs your attention" group is non-empty', self.md)
        self.assertIn("the run is interactive", self.md)

    def test_batch_cap_five_with_default_top_five(self):
        # FR-008/SC-006: up to five, default the top five in report order.
        self.assertIn("top five attention items in report order", self.md)
        self.assertIn("at most five attention items", self.md)

    def test_invalid_selection_is_rejected(self):
        # Edge case: >5 or a non-attention item is rejected with a clear message.
        self.assertIn("Pick up to five items", self.md)

    def test_next_batch_or_rerun_offered(self):
        # FR-010/SC-006: next five unvisited, or a re-run, while items remain.
        self.assertIn("next five", self.md)
        self.assertRegex(self.md, r"re-run of the tour")

    def test_tour_does_not_recollect(self):
        # FR-011: the tour reads the collected snapshot and never re-collects.
        self.assertRegex(self.md, r"never re-collect")

    def test_fanout_is_explicit_and_delegates(self):
        # FR-012/FR-014/FR-015: explicit choice; delegate to review/triage.
        self.assertIn("review --pr N", self.md)
        self.assertIn("triage --pr N", self.md)
        self.assertRegex(self.md, r"explicit choice")

    def test_discussion_is_textual_only(self):
        # FR-012: a Discussion gets a textual suggestion only (no launch).
        self.assertRegex(self.md, r"Discussion[\s\S]{0,160}?textual suggestion only")

    def test_bulk_handoff_is_an_explicit_unfiltered_list(self):
        # FR-013/FR-018: several PRs handed to bulk as one unfiltered list.
        self.assertIn("review --bulk --prs", self.md)
        self.assertRegex(self.md, r"[Pp]ass the list unfiltered")

    def test_fanout_requires_local_checkout(self):
        # FR-016: fan-out only inside a local checkout of the target repo.
        self.assertIn("local checkout of the target repository", self.md)
        self.assertIn("acting is unavailable", self.md)

    def test_degradation_prints_the_commands(self):
        # FR-019: where launch is unavailable, print the exact command(s).
        self.assertRegex(self.md, r"text handoff|print the exact command")


if __name__ == "__main__":
    unittest.main()
