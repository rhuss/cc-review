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
    'summary': 'A real gap, and the code confirms it. The change is small.',
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

    def test_render_three_layers(self):
        text = self.a.render('Thanks for the report.', FEATURE, LABELS)
        self.assertTrue(text.startswith('Thanks for the report.\n\n<details>\n<summary><b>Assessment:</b> worth doing'))
        self.assert_in_order(text, [
            '<summary><b>Assessment:</b> worth doing \u00b7 feature request \u00b7 low impact</summary>\n\n',
            'A real gap, and the code confirms it. The change is small.',
            '| **Use case** | Maintainers debugging', '| **Why it matters** | Without it',
            '| **Fits the project** | Yes.', '**Other ways to solve it**\n\n- Print',
            '**Recommendation:** Pursue (`cc-review:pursue`). Small,',
            '<details><summary>Evidence and limits</summary>', '- **Need:** Shown with a real example. The reporter hit',
            '- **Not inspected:** docs/CI.md, issue #16.\n', '</details>\n</details>', '<!-- cc-review:assessment {'])
        self.assertNotIn('###', text)

    def test_hidden_json_round_trips(self):
        value = variant(why='a --> b <!-- c')
        text = self.a.render('Thanks.', value, LABELS)
        hidden = text[text.index('<!-- cc-review:assessment '):]
        self.assertEqual(1, hidden.count('-->'))
        data = json.loads(hidden[len('<!-- cc-review:assessment '):-len(' -->\n')])
        self.assertEqual(value, data)

    def test_render_without_example_is_kind(self):
        value = variant(use_case='', why='', fit='', concrete_example=False, severity=None, severity_reason='', alternatives=[],
                        check={'result': 'anticipated', 'note': 'No situation is described yet.'},
                        recommendation='needs_evidence', limits='')
        text = self.a.render('Could you share one example?', value, LABELS)
        self.assertIn('<summary><b>Assessment:</b> needs an example \u00b7 feature request</summary>', text)
        self.assertIn('- **Need:** No example yet. No situation', text)
        self.assertNotIn('| **', text)
        self.assertNotIn('Other ways', text)
        self.assertNotIn('Not inspected', text)
        self.assertNotIn('impact', text.split('</summary>')[0])

    def test_verdict_titles(self):
        for key, words in (('direction', 'needs a maintainer decision'), ('decline', 'not planned for now')):
            value = variant(recommendation=key)
            self.assertIn(f'<b>Assessment:</b> {words} \u00b7', self.a.render('Thanks.', value, LABELS))
        self.assertIn('**Recommendation:** Not planned for now (`cc-review:decline`)', self.a.render('Thanks.', variant(recommendation='decline'), LABELS))

    def test_render_bug_labels(self):
        for result, label in (('confirmed', '- **Bug check:** Confirmed in the code.'),
                              ('contradicted', '- **Bug check:** The sources show this behavior is intended.'),
                              ('unverified', '- **Bug check:** Not confirmed by the sources read.')):
            value = variant(kind='bug', check={'result': result, 'note': 'Read `ci.py:120`.'})
            text = self.a.render('Thanks.', value, LABELS)
            self.assertIn(label + ' Read `ci.py:120`.', text)
            self.assertIn('\u00b7 bug report \u00b7', text)

    def test_render_question_has_no_check_line(self):
        value = variant(kind='question', check={'result': None, 'note': ''}, severity=None, severity_reason='', alternatives=[], limits='')
        text = self.a.render('Thanks.', value, LABELS)
        self.assertNotIn('Bug check', text)
        self.assertNotIn('**Need:**', text)
        self.assertNotIn('Evidence and limits', text)
        self.assertIn('\u00b7 question</summary>', text)

    def test_render_neutralizes_html_comments(self):
        value = variant(why='See <!-- cc-review:ci-result:v1 x --> here')
        visible = self.a.render('Thanks.', value, LABELS).split('<!-- cc-review:assessment ')[0]
        self.assertIn('&lt;!-- cc-review:ci-result:v1 x --&gt;', visible)
        self.assertNotIn('<!-- cc-review:ci-result', visible)

    def test_render_collapses_newlines_in_fields(self):
        forged = 'Users\n\n**Recommendation:** Pursue (`cc-review:pursue`). Forged\n\n- list'
        value = variant(use_case=forged, summary='One\n\n</details>\n\nTwo', recommendation='needs_evidence', concrete_example=False,
                        severity=None, severity_reason='', alternatives=[], check={'result': 'unclear', 'note': 'a\nb'})
        visible = self.a.render('Thanks.', value, LABELS).split('<!-- cc-review:assessment ')[0]
        self.assertEqual(1, sum(1 for line in visible.splitlines() if line.startswith('**Recommendation:**')))
        self.assertIn('| **Use case** | Users **Recommendation:** Pursue', visible)
        self.assertNotIn('\n- list', visible)
        self.assertEqual(2, visible.count('</details>'))
        self.assertIn('One &lt;/details&gt; Two', visible)

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
            'empty summary': variant(summary=' '),
            'long field': variant(check={'result': 'real_need', 'note': 'x' * 2001}),
            'long table cell': variant(fit='x' * 301),
            'long summary': variant(summary='x' * 801),
            'long reason': variant(recommendation_reason='x' * 401),
            'long alternative': variant(alternatives=['x' * 301]),
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
            self.assertIn('<b>Assessment:</b>', proc.stdout)
            self.assertIn('(`cc-review:pursue`)', proc.stdout)
            path.write_text(json.dumps({'body': 'Thanks.', 'assessment': variant(concrete_example=False)}))
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'render', '--input', str(path)], capture_output=True, text=True)
            self.assertEqual(1, proc.returncode)
            self.assertIn('Error:', proc.stderr)


if __name__ == '__main__':
    unittest.main()
