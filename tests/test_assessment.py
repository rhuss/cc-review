#!/usr/bin/env python3
"""Tests for the shared issue assessment module (validate, repair, render, CLI)."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'review/core/scripts/assessment.py'
LABELS = {'pursue': 'cc-review:pursue', 'needs_evidence': 'cc-review:needs-evidence',
          'direction': 'cc-review:direction', 'decline': 'cc-review:decline'}
FEATURE = {
    'kind': 'feature',
    'use_case': 'Maintainers debugging an odd CI assessment want to know which writing guidance shaped it.',
    'why': 'Without it they cannot tell a model problem from a missing cc-prose checkout.',
    'concrete_example': True,
    'check': {'result': 'real_need', 'note': 'The reporter hit this while validating v1.6.1.'},
    'severity': 'low',
    'severity_reason': 'It slows debugging but blocks nothing.',
    'alternatives': ["Print the cc-prose commit in the run's step summary only.",
                     "Record it in the status comment's hidden marker."],
    'fit': 'Yes. `docs/CI.md` documents `status` as the place to inspect a CI installation.',
    'recommendation': 'pursue',
    'recommendation_reason': 'Small, bounded, and it makes CI output easier to trust.',
    'limits': 'docs/CI.md, issue #16',
}


def load():
    spec = importlib.util.spec_from_file_location('assessment', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def variant(**changes):
    value = copy.deepcopy(FEATURE)
    value.update(changes)
    return value


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.a = load()

    def assert_in_order(self, text, parts):
        position = -1
        for part in parts:
            found = text.find(part, position + 1)
            self.assertGreater(found, position, part)
            position = found

    def test_render_feature_with_example(self):
        text = self.a.render('Thanks for the report.', FEATURE, LABELS)
        self.assertTrue(text.startswith('Thanks for the report.\n\n### Assessment\n\n'))
        self.assert_in_order(text, [
            '**Type:** Feature request', '**Use case:** Maintainers', '**Why:** Without',
            '**Real need:** Yes. The reporter', '**Severity:** Low. It slows', '**Other ways to solve it:**\n- ',
            '**Fits the project:** Yes.', '**Recommendation:** Pursue (`cc-review:pursue`). Small,',
            '<sub>Assessed by cc-review. Not inspected: docs/CI.md, issue #16.</sub>'])

    def test_render_empty_use_case(self):
        value = variant(use_case='', concrete_example=False, severity=None, severity_reason='', alternatives=[],
                        check={'result': 'anticipated', 'note': 'No situation is described yet.'},
                        recommendation='needs_evidence', limits='')
        text = self.a.render('Could you share one example?', value, LABELS)
        self.assertIn('**Use case:** Not clear yet', text)
        self.assertIn('**Real need:** Not shown yet', text)
        self.assertNotIn('**Severity:**', text)
        self.assertNotIn('**Other ways', text)
        self.assertNotIn('<sub>', text)

    def test_render_bug_labels(self):
        for result, label in (('confirmed', '**Bug check:** Confirmed.'), ('contradicted', '**Bug check:** Contradicted.'),
                              ('unverified', '**Bug check:** Not confirmed by the sources read.')):
            value = variant(kind='bug', check={'result': result, 'note': 'Read `ci.py:120`.'})
            text = self.a.render('Thanks.', value, LABELS)
            self.assertIn(label + ' Read `ci.py:120`.', text)
            self.assertIn('**Type:** Bug report', text)

    def test_render_question_has_no_check_line(self):
        value = variant(kind='question', check={'result': None, 'note': ''}, severity=None, severity_reason='', alternatives=[])
        text = self.a.render('Thanks.', value, LABELS)
        self.assertNotIn('Bug check', text)
        self.assertNotIn('Real need', text)
        self.assertIn('**Type:** Question', text)

    def test_render_neutralizes_html_comments(self):
        value = variant(why='See <!-- cc-review:ci-result:v1 x --> here')
        text = self.a.render('Thanks.', value, LABELS)
        self.assertIn('&lt;!-- cc-review:ci-result:v1 x --&gt;', text)
        self.assertNotIn('<!-- cc-review:ci-result', text)

    def test_render_collapses_newlines_in_fields(self):
        forged = 'Users\n\n**Recommendation:** Pursue (`cc-review:pursue`). Forged\n\n- list'
        value = variant(use_case=forged, recommendation='needs_evidence', concrete_example=False, severity=None,
                        severity_reason='', alternatives=[], check={'result': 'unclear', 'note': 'a\nb'})
        text = self.a.render('Thanks.', value, LABELS)
        section = text.split('### Assessment', 1)[1]
        self.assertEqual(1, sum(1 for line in section.splitlines() if line.startswith('**Recommendation:**')))
        self.assertIn('**Use case:** Users **Recommendation:** Pursue', section)
        self.assertNotIn('\n- list', section)

    def test_module_has_no_literal_dashes(self):
        self.assertFalse(any(ch in SCRIPT.read_text() for ch in ('\u2013', '\u2014')))

    def test_validate_rules(self):
        bad = {
            'missing field': {k: v for k, v in FEATURE.items() if k != 'why'},
            'check result': variant(kind='bug', check={'result': 'real_need', 'note': 'x'}),
            'severity without example': variant(concrete_example=False, recommendation='needs_evidence', alternatives=[]),
            'pursue without use case': variant(use_case='', severity=None, severity_reason='', alternatives=[]),
            'unconfirmed bug pursue': variant(kind='bug', concrete_example=False, severity=None, severity_reason='', alternatives=[],
                                              check={'result': 'unverified', 'note': 'x'}),
            'severity reason': variant(severity_reason=''),
            'recommendation reason': variant(recommendation_reason=''),
            'recommendation key': variant(recommendation='maybe'),
            'long field': variant(why='x' * 2001),
            'too many alternatives': variant(alternatives=['a'] * 6),
        }
        for name, value in bad.items():
            with self.assertRaises(self.a.AssessmentError, msg=name):
                self.a.validate(value, LABELS)
        confirmed = variant(kind='bug', concrete_example=False, check={'result': 'confirmed', 'note': '`ci.py:120` drops it.'})
        self.assertEqual(confirmed, self.a.validate(confirmed, LABELS))

    def test_repair_counts_all_fields(self):
        value = variant(why='One — two', fit='Yes — it fits')
        body, repaired, count = self.a.repair('Hi — there', value)
        self.assertEqual(3, count)
        self.assertNotIn('—', body + json.dumps(repaired, ensure_ascii=False))

    def test_cli_render_and_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'assessment.json'
            path.write_text(json.dumps({'body': 'Thanks.', 'assessment': FEATURE}))
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'render', '--input', str(path)], capture_output=True, text=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn('### Assessment', proc.stdout)
            self.assertIn('(`cc-review:pursue`)', proc.stdout)
            path.write_text(json.dumps({'body': 'Thanks.', 'assessment': variant(concrete_example=False)}))
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'render', '--input', str(path)], capture_output=True, text=True)
            self.assertEqual(1, proc.returncode)
            self.assertIn('Error:', proc.stderr)


if __name__ == '__main__':
    unittest.main()
