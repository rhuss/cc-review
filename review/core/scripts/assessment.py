#!/usr/bin/env python3
"""Validate and render a structured issue assessment.

Shared by the CI publisher (ci.py) and the manual issue command.

Usage: assessment.py render --input FILE [--config CI_YML]

FILE holds {"body": "<reply to the reporter>", "assessment": {...}}. The
rendered comment (reply plus an "### Assessment" section) goes to stdout.
Exit codes: 0 success, 1 invalid assessment or input, 2 usage error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
KINDS = ('bug', 'feature', 'question', 'other')
CHECK_RESULTS = {'bug': ('confirmed', 'contradicted', 'unverified'),
                 'feature': ('real_need', 'anticipated', 'unclear'),
                 'question': (None,), 'other': (None,)}
SEVERITIES = ('low', 'medium', 'high')
TEXT_FIELDS = ('use_case', 'why', 'severity_reason', 'fit', 'recommendation_reason', 'limits')
FIELDS = ('kind', 'use_case', 'why', 'concrete_example', 'check', 'severity', 'severity_reason',
          'alternatives', 'fit', 'recommendation', 'recommendation_reason', 'limits')
TEXT_LIMIT = 2000
ALTERNATIVES_LIMIT = 5
ALTERNATIVE_LIMIT = 500

KIND_LABELS = {'bug': 'Bug report', 'feature': 'Feature request', 'question': 'Question', 'other': 'Other'}
BUG_CHECK = {'confirmed': 'Confirmed.', 'contradicted': 'Contradicted.', 'unverified': 'Not confirmed by the sources read.'}
REAL_NEED = {'real_need': 'Yes.', 'anticipated': 'Not shown yet.', 'unclear': 'Unclear.'}
RECOMMENDATIONS = {'pursue': 'Pursue', 'needs_evidence': 'Needs more evidence',
                   'direction': 'Needs a direction decision', 'decline': 'Decline'}

CODE_SPANS = re.compile(r'(```.*?```|`[^`\n]*`)', re.S)
DASH_RULES = (
    (re.compile(r'(\d)[ \t]*[\u2013\u2014][ \t]*(\d)'), r'\1-\2'),        # numeric range
    (re.compile(r'[ \t]*[\u2013\u2014][ \t]*(?=[.,;:!?)])'), ''),          # dash before punctuation
    (re.compile(r'^([ \t]*)[\u2013\u2014][ \t]+', re.M), r'\1- '),          # dash used as a bullet
    (re.compile(r'[ \t]*[\u2013\u2014][ \t]*'), ', '),                     # aside or clause break
)


class AssessmentError(ValueError):
    """An assessment breaks a rule; the message names the rule."""


def repair_dashes(text):
    """Replace em and en dashes outside code with plain punctuation; return (text, count)."""
    count = 0

    def fix(part):
        nonlocal count
        for pattern, replacement in DASH_RULES:
            part, n = pattern.subn(replacement, part)
            count += n
        return part
    pieces = CODE_SPANS.split(text)
    return ''.join(p if i % 2 else fix(p) for i, p in enumerate(pieces)), count


def _text(value, name, limit=TEXT_LIMIT):
    if not isinstance(value, str):
        raise AssessmentError(f'assessment.{name} must be text.')
    if len(value) > limit:
        raise AssessmentError(f'assessment.{name} exceeds {limit} characters.')
    return value


def validate(assessment, label_keys):
    """Check types and the judgment rules; return the assessment unchanged."""
    if not isinstance(assessment, dict):
        raise AssessmentError('assessment must be an object.')
    missing = [f for f in FIELDS if f not in assessment]
    if missing:
        raise AssessmentError('assessment is missing ' + ', '.join(missing) + '.')
    extra = sorted(set(assessment) - set(FIELDS))
    if extra:
        raise AssessmentError('assessment has unknown fields ' + ', '.join(extra) + '.')
    kind = assessment['kind']
    if kind not in KINDS:
        raise AssessmentError('assessment.kind must be one of ' + ', '.join(KINDS) + '.')
    for name in TEXT_FIELDS:
        _text(assessment[name], name)
    if type(assessment['concrete_example']) is not bool:
        raise AssessmentError('assessment.concrete_example must be true or false.')
    check = assessment['check']
    if not isinstance(check, dict) or set(check) != {'result', 'note'}:
        raise AssessmentError('assessment.check must have result and note.')
    _text(check['note'], 'check.note')
    if check['result'] not in CHECK_RESULTS[kind]:
        raise AssessmentError(f'assessment.check.result {check["result"]!r} is not allowed for a {kind}.')
    if assessment['severity'] is not None and assessment['severity'] not in SEVERITIES:
        raise AssessmentError('assessment.severity must be low, medium, high or null.')
    alternatives = assessment['alternatives']
    if not isinstance(alternatives, list) or len(alternatives) > ALTERNATIVES_LIMIT:
        raise AssessmentError(f'assessment.alternatives must be a list of at most {ALTERNATIVES_LIMIT} entries.')
    for item in alternatives:
        _text(item, 'alternatives entry', ALTERNATIVE_LIMIT)
    if assessment['recommendation'] not in label_keys:
        raise AssessmentError('assessment.recommendation must be a configured classification key.')
    if not assessment['recommendation_reason'].strip():
        raise AssessmentError('assessment.recommendation_reason must state why.')
    if assessment['severity'] is not None and not assessment['severity_reason'].strip():
        raise AssessmentError('assessment.severity needs a severity_reason.')
    # The example gate: without a concrete case, no severity, no alternatives, no pursue.
    gated = not assessment['concrete_example'] or not assessment['use_case'].strip()
    if kind == 'bug':
        gated = not assessment['concrete_example'] and check['result'] != 'confirmed'
    if gated and (assessment['severity'] is not None or alternatives or assessment['recommendation'] == 'pursue'):
        raise AssessmentError('Without a concrete example (or reproduction steps or a confirmed bug), '
                              'severity and alternatives stay empty and the recommendation cannot be pursue.')
    return assessment


def repair(body, assessment):
    """Dash-repair the reply and every free-text field; return (body, assessment, count)."""
    body, total = repair_dashes(body)
    fixed = dict(assessment)
    for name in TEXT_FIELDS:
        fixed[name], n = repair_dashes(fixed[name])
        total += n
    fixed['check'] = dict(fixed['check'])
    fixed['check']['note'], n = repair_dashes(fixed['check']['note'])
    total += n
    alternatives = []
    for item in fixed['alternatives']:
        item, n = repair_dashes(item)
        total += n
        alternatives.append(item)
    fixed['alternatives'] = alternatives
    return body, fixed, total


def _safe(text):
    return str(text).replace('<!--', '&lt;!--').replace('-->', '--&gt;')


def _flat(text):
    # One line per labeled field: issue text must not be able to forge labels or lists.
    return _safe(' '.join(str(text).split()))


def _with_note(label, note):
    return (label + ' ' + note.strip()).strip() if note.strip() else label


def render(body, assessment, labels):
    """Render the reply plus the Assessment section as Markdown."""
    a = assessment
    lines = ['### Assessment', '', f"**Type:** {KIND_LABELS[a['kind']]}",
             '**Use case:** ' + (_flat(a['use_case']) or 'Not clear yet'),
             '**Why:** ' + (_flat(a['why']) or 'Not clear yet')]
    result, note = a['check']['result'], _flat(a['check']['note'])
    if a['kind'] == 'bug':
        lines.append('**Bug check:** ' + _with_note(BUG_CHECK[result], note))
    elif a['kind'] == 'feature':
        lines.append('**Real need:** ' + _with_note(REAL_NEED[result], note))
    if a['severity'] is not None:
        lines.append(f"**Severity:** {a['severity'].capitalize()}. " + _flat(a['severity_reason']))
    if a['alternatives']:
        lines.append('**Other ways to solve it:**')
        lines += ['- ' + _flat(item) for item in a['alternatives']]
        lines.append('')
    if a['fit'].strip():
        lines.append('**Fits the project:** ' + _flat(a['fit']))
    key = a['recommendation']
    lines.append(f"**Recommendation:** {RECOMMENDATIONS.get(key, key)} (`{labels[key]}`). "
                 + _flat(a['recommendation_reason']))
    if a['limits'].strip():
        lines += ['', '<sub>Assessed by cc-review. Not inspected: ' + _flat(a['limits']).rstrip('.') + '.</sub>']
    # Markdown needs a line break between labeled lines; two trailing spaces keep them as one block.
    section = '\n'.join(line + '  ' if line.startswith('**') and not line.endswith(':**') else line for line in lines)
    return _safe(body.strip()) + '\n\n' + section.rstrip() + '\n'


def load_labels(config_path):
    path = Path(config_path) if config_path else CORE.parent / 'config/ci.yml'
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        raise AssessmentError(f'Cannot read labels from {path}; pass --config with a JSON ci.yml.')
    labels = value.get('labels') if isinstance(value, dict) else None
    if not isinstance(labels, dict) or not labels:
        raise AssessmentError(f'{path} has no labels mapping.')
    return labels


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('render', help='validate and render an assessment file')
    p.add_argument('--input', required=True)
    p.add_argument('--config', default='')
    args = parser.parse_args(argv)
    try:
        data = json.loads(Path(args.input).read_text())
        if not isinstance(data, dict) or not isinstance(data.get('body'), str):
            raise AssessmentError('Input needs a "body" text and an "assessment" object.')
        labels = load_labels(args.config)
        validate(data.get('assessment'), labels)
        body, fixed, _ = repair(data['body'], data['assessment'])
        sys.stdout.write(render(body, fixed, labels))
        return 0
    except (OSError, ValueError) as error:
        print('Error: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
