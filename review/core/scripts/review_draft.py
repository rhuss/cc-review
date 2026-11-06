#!/usr/bin/env python3
"""Draft, check and fingerprint a cc-review PR review before it is posted.

The review text is assembled from a slots file: the prose rewrite may change
slot text only, so labels, footers, counts, the attribution statement, the run
marker and the completion lines are produced here, by construction. Nothing in
this module talks to the hosting service; every file is written atomically.

Exit codes: 0 success, 1 validation failure (lint findings, new conversation
items), 2 usage or input error (message on stderr).
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


SEVERITIES = ('Critical', 'Important', 'Minor', 'Notable')
OUTCOMES = ('passed', 'failed', 'no-test-command')
EVENTS = ('COMMENT', 'REQUEST_CHANGES')
SECTION_ORDER = ('## cc-review Summary', '### Follow-up progress', '### What Went Well',
                 '### Findings', '### Review Details')
REQUIRED_SECTIONS = ('## cc-review Summary', '### Findings', '### Review Details')

# Attribution sentences. Every clause maps to one recorded fact.
CURATED = ("I went through these findings one by one and selected the ones posted here; "
           "cc-review's reviewer agents produced them.")
NOT_CURATED = ("These findings were produced by cc-review's reviewer agents and posted "
               "without a per-finding review.")
NO_TEST_COMMAND = 'No test command was detected, so no tests were run.'
REPRO = 'Failure scenarios were derived from reading the code and were not executed.'
ATTRIBUTION_LEADS = ('I went through these findings one by one',
                     "These findings were produced by cc-review's reviewer agents")
TRUNCATED_REASON = 'Truncated: exceeded maximum inline comment limit ({limit})'

# Kinds of thread-actions.json entries. An entry without "kind" is a
# resolution entry (the reply that explains a verified fix, then resolve).
# The continuation kinds are Follow-up Continuity responses: a reply in an
# existing review thread, or a PR conversation comment for a summary-only
# discussion. Both never resolve anything.
ACTION_KINDS = ('resolution', 'continuation', 'pr-comment')
CONTINUATION_KINDS = ('continuation', 'pr-comment')

# "I ran", "I've tested", "i verified", "I also ran", "I have just checked"; the
# text is matched after typographic apostrophes became plain ones (_claim_text)
CLAIM = re.compile(r"\b[Ii](?:'ve| have| had)?(?:\s+(?:also|just|already|personally|actually|then|\w+ly))?"
                   r"\s+(ran|run|tested|verified|executed|curated|checked|"
                   r"reproduced|confirmed|went through|selected)\b")
CURATION_VERBS = {'curated', 'went through', 'selected'}
EXECUTION_VERBS = {'ran', 'run', 'tested', 'executed'}
# A claim that a named test command passed (a known tool or a command of
# executed[]) is checked by _named_results; these patterns are the generic ones
TEST_TOOLS = ('go test', 'npm test', 'pytest', 'make test', 'cargo test')
RESULT_PATTERNS = (
    re.compile(r'\btests? (?:all )?(?:pass|passed|passing|succeed|succeeded)\b', re.I),
    re.compile(r'\bpassed at this head\b', re.I),
)
NEGATION = re.compile(r"\b(?:not|never|no longer|fail\w*)\b|n't\b", re.I)
# FR-009 allows a result "labeled as reported by an agent and not verified":
# a sentence that names an agent or reviewer as the reporter and says the
# result was not verified is not a result claim of the run
AGENT_REPORT = re.compile(r'\b(?:agents?|reviewers?)\b.*\breport', re.I)
UNVERIFIED = re.compile(r'\b(?:not (?:been )?verified|unverified|(?:nobody|no one) verified)\b', re.I)


def _without_agent_reports(text):
    """The text minus sentences that label a result as an unverified agent report."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return ' '.join(s for s in sentences if not (AGENT_REPORT.search(s) and UNVERIFIED.search(s)))


class UsageError(Exception):
    """Bad arguments or unreadable input (exit 2)."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _sha(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.' + path.name + '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_json(path, value):
    _write(path, json.dumps(value, indent=2, ensure_ascii=False) + '\n')


_MISSING = object()


def _load(path, default=_MISSING):
    path = Path(path)
    if not path.exists():
        if default is not _MISSING:
            return default
        raise UsageError(str(path) + ' does not exist')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError) as error:
        raise UsageError(str(path) + ' is not valid JSON: ' + str(error))


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Run facts
# ---------------------------------------------------------------------------

def validate_executed(entry):
    if not isinstance(entry, dict):
        raise UsageError('an executed entry must be a JSON object')
    if not _int(entry.get('round')) or entry['round'] < 1:
        raise UsageError('executed.round must be an integer >= 1')
    if entry.get('outcome') not in OUTCOMES:
        raise UsageError('executed.outcome must be one of: ' + ', '.join(OUTCOMES))
    command = entry.get('command', '')
    if not isinstance(command, str):
        raise UsageError('executed.command must be a string')
    if entry['outcome'] != 'no-test-command' and not command.strip():
        raise UsageError('executed.command may be empty only for no-test-command')
    return dict(round=entry['round'], command=command, outcome=entry['outcome'])


def load_facts(path):
    facts = _load(path, None)
    if facts is None:
        return dict(curated=False, executed=[])
    if not isinstance(facts, dict):
        raise UsageError('facts must be a JSON object')
    curated = facts.get('curated', False)
    executed = facts.get('executed', [])
    if not isinstance(curated, bool) or not isinstance(executed, list):
        raise UsageError('facts.curated must be a boolean and facts.executed an array')
    return dict(curated=curated, executed=[validate_executed(e) for e in executed])


def cmd_facts_set(args):
    facts = load_facts(args.facts)
    if args.curated is not None:
        facts['curated'] = args.curated == 'true'
    else:
        try:
            entry = validate_executed(json.loads(args.executed))
        except ValueError as error:
            raise UsageError('--executed is not valid JSON: ' + str(error))
        # One outcome per fix round: a round that runs again (a resumed run)
        # replaces its earlier entry instead of adding a second one
        facts['executed'] = [e for e in facts['executed'] if e['round'] != entry['round']] + [entry]
        facts['executed'].sort(key=lambda e: e['round'])
    _write_json(args.facts, facts)
    return 0


def _ran(facts):
    return any(e['outcome'] in ('passed', 'failed') for e in facts['executed'])


def _named_results(text, facts):
    """Claims that a named test command passed, and the text without them.

    Returns ([(phrase, command)], rest). A command is named by a known test
    tool or by a command recorded in executed[]; longer names win, so
    "go test ./..." is named as a whole, and arguments that follow a name
    (words with "-", "." or "/", such as "./pkg/...") belong to the command.
    A claim ends at the first "pass" word on the same line.
    """
    names = {' '.join(name.split()) for name in TEST_TOOLS}
    names |= {' '.join(e['command'].split()) for e in facts['executed'] if e['command'].strip()}
    alternatives = '|'.join(r'[ \t]+'.join(re.escape(word) for word in name.split())
                            for name in sorted(names, key=len, reverse=True))
    pattern = re.compile(r'(?<![\w./-])(' + alternatives + r')(?![\w-])((?:[ \t]+(?:[-.]\S*|\S*/\S*))*)'
                         r'[^\n]*?\b(?:pass|passes|passed|passing)\b', re.I)
    claims = [(match.group(0), ' '.join((match.group(1) + match.group(2)).split()))
              for match in pattern.finditer(text)]
    return claims, pattern.sub(' ', text)


def _passed_command(facts, command):
    """The latest fix round ran this command (or a command it names) and it passed."""
    executed = facts['executed']
    if not executed:
        return False
    latest = max(e['round'] for e in executed)
    command = command.lower()
    for entry in executed:
        recorded = ' '.join(entry['command'].split()).lower()
        if entry['round'] == latest and entry['outcome'] == 'passed' and recorded \
                and (recorded == command or recorded.startswith(command + ' ')):
            return True
    return False


def _passed(facts):
    """The latest fix round ran its tests and they passed."""
    executed = facts['executed']
    if not executed:
        return False
    latest = max(e['round'] for e in executed)
    outcomes = {e['outcome'] for e in executed if e['round'] == latest}
    return outcomes == {'passed'}


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

def _code(text):
    fence = '``' if '`' in text else '`'
    pad = ' ' if fence == '``' else ''
    return fence + pad + text + pad + fence


def attribution(facts, repro=False):
    parts = [CURATED if facts['curated'] else NOT_CURATED]
    executed = facts['executed']
    if executed:
        latest = max(e['round'] for e in executed)
        for entry in executed:
            if entry['round'] != latest:
                continue
            if entry['outcome'] == 'no-test-command':
                sentence = NO_TEST_COMMAND
            else:
                sentence = 'The run executed {} in fix round {}: {}.'.format(
                    _code(entry['command'].strip()), entry['round'], entry['outcome'])
            if sentence not in parts:
                parts.append(sentence)
    if repro:
        parts.append(REPRO)
    return ' '.join(parts)


def cmd_attribution(args):
    # Diagnostic entry point: assemble and lint render the statement
    # themselves, so no command calls this; it shows what a draft would carry
    print(attribution(load_facts(args.facts), args.repro))
    return 0


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _text(value):
    return value.strip() if isinstance(value, str) else ''


def _cell(value, limit=None):
    text = ' '.join(_text(value).split())
    if limit and len(text) > limit:
        text = text[:limit - 4].rstrip()
        # Close a code span the cut left open, so it cannot swallow the
        # following prose when the check strips inline code
        text += ('`' if text.count('`') % 2 else '') + '...'
    return text.replace('|', '\\|')


def comment_body(comment):
    return ('**{}**: {}\n\n**Why this matters**: {}\n\n**Suggested fix**: {}\n\n_Source: {}_'.format(
        comment['severity'], _text(comment.get('what')), _text(comment.get('why')),
        _text(comment.get('fix')), _text(comment.get('source'))))


def _validate_slots(slots):
    if not isinstance(slots, dict):
        raise UsageError('slots must be a JSON object')
    if slots.get('event') not in EVENTS:
        raise UsageError('slots.event must be COMMENT or REQUEST_CHANGES')
    if not _text(slots.get('run_marker')):
        raise UsageError('slots.run_marker is required')
    for name in ('comments', 'summary_only'):
        if not isinstance(slots.get(name, []), list):
            raise UsageError('slots.' + name + ' must be an array')
    for comment in slots.get('comments', []):
        if (not isinstance(comment, dict) or not _text(comment.get('path'))
                or not _int(comment.get('line')) or comment['line'] < 1
                or comment.get('severity') not in SEVERITIES):
            raise UsageError('every slots comment needs path, line >= 1 and a severity')
        start = comment.get('start_line')
        if start is not None and (not _int(start) or start < 1 or start > comment['line']):
            raise UsageError('slots comment start_line must be between 1 and line')
    for item in slots.get('summary_only', []):
        if not isinstance(item, dict) or item.get('severity') not in SEVERITIES:
            raise UsageError('every summary-only finding needs a severity')
    if not isinstance(slots.get('went_well') or [], list):
        raise UsageError('slots.went_well must be an array')


def _where(item):
    """file:line of a summary-only finding, or the file alone without a line."""
    line = item.get('line')
    path = _text(item.get('file'))
    return '{}:{}'.format(path, line) if _int(line) else path


def _location(comment):
    start = comment.get('start_line')
    return start if start else comment['line']


def plan(slots, max_comments=None):
    """Inline comments and summary-only findings after removal and truncation."""
    active = [c for c in slots.get('comments', []) if not c.get('removed')]
    removed = len(slots.get('comments', [])) - len(active)
    summary_only = [dict(s) for s in slots.get('summary_only', [])]
    if max_comments is not None and len(active) > max_comments:
        rank = {s: i for i, s in enumerate(SEVERITIES)}
        ordered = sorted(range(len(active)), key=lambda i: rank[active[i]['severity']])
        keep = set(ordered[:max_comments])
        reason = TRUNCATED_REASON.format(limit=max_comments)
        for i in ordered[max_comments:]:
            c = active[i]
            summary_only.append(dict(id=c.get('id'), severity=c['severity'], file=c['path'],
                                     line=_location(c), description=_text(c.get('what')),
                                     source=_text(c.get('source')),
                                     source_agent=c.get('source_agent'), reason=reason))
        active = [c for i, c in enumerate(active) if i in keep]
    return active, summary_only, removed


def summary_body(slots, facts, active, summary_only, removed):
    lines = ['## cc-review Summary', '']
    follow_up = _text(slots.get('follow_up'))
    if follow_up:
        lines += ['### Follow-up progress', '', follow_up, '']
    bullets = [re.sub(r'^\s*[-*]\s+', '', _text(b)) for b in slots.get('went_well') or []]
    bullets = [b for b in bullets if b]
    if bullets:
        lines += ['### What Went Well', ''] + ['- ' + b for b in bullets] + ['']
    lines += ['### Findings', '']
    rows = [(c['severity'], '{}:{}'.format(c['path'], _location(c)), c.get('what'),
             c.get('source_agent') or c.get('source')) for c in active]
    rows += [(s['severity'], _where(s), s.get('description'), s.get('source_agent') or s.get('source')) for s in summary_only]
    if rows:
        lines += ['| Severity | File | Description | Source |', '|----------|------|-------------|--------|']
        lines += ['| {} | {} | {} | {} |'.format(sev, _cell(loc), _cell(desc, 100), _cell(src))
                  for sev, loc, desc, src in rows]
    else:
        lines.append('No findings are posted in this review.')
    lines.append('')
    if summary_only:
        lines += ['Findings not posted as inline comments:', '']
        for s in summary_only:
            reason = _text(s.get('reason')).rstrip('.')
            lines.append('- **{}** `{}`: {} (not inline: {}; source: {})'.format(
                s['severity'], _where(s), _text(s.get('description')),
                reason or 'no reason recorded', _text(s.get('source')) or 'unknown'))
        lines.append('')
    statement = _text(slots.get('attribution_override')) or attribution(facts, bool(slots.get('repro_present')))
    counts = slots.get('counts') or {}
    rejected = counts.get('rejected', 0) if _int(counts.get('rejected', 0)) else 0
    reviewers = [r for r in slots.get('reviewers') or [] if _text(r)]
    lines += ['### Review Details', '', statement, '',
              '- **Findings posted**: {}'.format(len(active) + len(summary_only)),
              '- **Findings reviewed and not posted**: {}'.format(rejected + removed),
              '- **Gate outcome**: {}'.format(_text(slots.get('gate')) or 'unknown'),
              '- **Participating reviewers**: {}'.format(', '.join(reviewers) or 'none'),
              '', '<!-- cc-review:run-id:{} -->'.format(_text(slots['run_marker']))]
    completion = _text(slots.get('completion'))
    if completion:
        lines.append(completion)
    return '\n'.join(lines)


def payload_comment(comment):
    start = comment.get('start_line')
    if start and start < comment['line']:
        return dict(path=comment['path'], start_line=start, line=comment['line'], side='RIGHT',
                    start_side='RIGHT', body=comment_body(comment))
    return dict(path=comment['path'], line=comment['line'], side='RIGHT', body=comment_body(comment))


def assemble(slots, facts, max_comments=None):
    _validate_slots(slots)
    active, summary_only, removed = plan(slots, max_comments)
    payload = dict(body=summary_body(slots, facts, active, summary_only, removed),
                   event=slots['event'], comments=[payload_comment(c) for c in active])
    if _text(slots.get('commit_id')):
        payload['commit_id'] = _text(slots['commit_id'])
    return payload, summary_only


def action_kind(action):
    return action.get('kind') or 'resolution'


def validate_actions(actions):
    """The entries of thread-actions.json, checked; raises UsageError."""
    if not isinstance(actions, list):
        raise UsageError('thread-actions.json must be a JSON array')
    # One entry per thread and one PR comment per source: a second entry would
    # be shown in the preview but skipped at post time as already done
    seen = set()
    for index, action in enumerate(actions, 1):
        where = 'thread action {}'.format(index)
        if not isinstance(action, dict):
            raise UsageError(where + ' must be a JSON object')
        kind = action_kind(action)
        if kind not in ACTION_KINDS:
            raise UsageError(where + ': kind must be one of: ' + ', '.join(ACTION_KINDS))
        if not isinstance(action.get('reply_body', ''), str):
            raise UsageError(where + ': reply_body must be a string')
        if kind == 'pr-comment':
            if action.get('thread_id') is not None:
                raise UsageError(where + ': a pr-comment entry has no thread_id')
            if not _text(action.get('source_id')):
                raise UsageError(where + ': a pr-comment entry needs the source_id of the discussion it continues')
        elif not _text(action.get('thread_id')):
            raise UsageError(where + ': a thread entry needs a thread_id')
        if kind in CONTINUATION_KINDS:
            if not _text(action.get('reply_body')):
                raise UsageError(where + ': a continuation entry needs a reply_body')
            if action.get('resolve'):
                raise UsageError(where + ': a continuation entry never resolves a thread')
        key = (('source', _text(action.get('source_id'))) if kind == 'pr-comment'
               else ('thread', _text(action.get('thread_id'))))
        if key in seen:
            raise UsageError(where + ': a second entry for {} {}; merge it into one entry'.format(*key))
        seen.add(key)
    return actions


def _action_where(index, action):
    if action_kind(action) == 'pr-comment':
        return 'thread action {} (PR comment)'.format(index)
    return 'thread action {} (thread {})'.format(index, action.get('thread_id'))


def fingerprint(draft):
    """SHA-256 of the payload and the thread actions; a draft of thread
    actions alone (no review is posted) has no payload.json."""
    draft = Path(draft)
    payload = _load(draft / 'payload.json', None)
    actions = _load(draft / 'thread-actions.json', [])
    if payload is None and not (draft / 'thread-actions.json').exists():
        raise UsageError(str(draft) + ' has neither payload.json nor thread-actions.json')
    return _sha(dict(payload=payload, thread_actions=actions))


def cmd_assemble(args):
    out = Path(args.out)
    slots = _load(args.slots)
    facts = load_facts(args.facts)
    previous = _load(out / 'draft.json', {})
    previous = previous if isinstance(previous, dict) else {}
    # A re-assembly of the same draft (redraft, edit) keeps its check count and
    # inline comment limit; a draft rebuilt from other inputs starts afresh
    if previous.get('inputs_key') != args.inputs_key:
        previous = {}
    attempts = previous.get('lint_attempts', 0)
    limit = args.max_comments if args.max_comments is not None else previous.get('max_comments')
    if limit is not None and (not _int(limit) or limit < 0):
        raise UsageError('--max-comments must be a non-negative integer')
    payload, summary_only = assemble(slots, facts, limit)
    _write_json(out / 'payload.json', payload)
    if not (out / 'thread-actions.json').exists():
        _write_json(out / 'thread-actions.json', [])
    # The check result and the preview belong to the previous payload
    for stale in ('lint.json', 'preview.md'):
        try:
            (out / stale).unlink()
        except FileNotFoundError:
            pass
    sha = fingerprint(out)
    _write_json(out / 'draft.json', dict(inputs_key=args.inputs_key, fingerprint=sha,
                                         lint_attempts=attempts if _int(attempts) else 0,
                                         max_comments=limit, summary_only=summary_only))
    print('FINGERPRINT ' + sha)
    return 0


def cmd_fingerprint(args):
    print(fingerprint(args.draft))
    return 0


def cmd_inputs_key(args):
    findings = _load(args.findings)
    if not isinstance(findings, list) or any(not isinstance(f, dict) or not _text(f.get('id')) for f in findings):
        raise UsageError('--findings must be a JSON array of findings with an id')
    print(_sha(dict(expected_head=args.expected_head,
                    finding_ids_to_post=sorted(f['id'] for f in findings),
                    facts=load_facts(args.facts))))
    return 0


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def _quote(text):
    return '\n'.join('> ' + line if line else '>' for line in text.splitlines()) or '>'


def _preview_tail(actions, lint):
    """The proposed thread actions and the remaining check findings."""
    out = ['## Proposed thread actions', '']
    if not actions:
        out += ['None.', '']
    for action in actions:
        kind = action_kind(action)
        if kind == 'pr-comment':
            link = _text(action.get('source_url'))
            head = '- PR conversation comment, continues `{}`{}'.format(
                _text(action.get('source_id')), ' ({})'.format(link) if link else '')
        elif kind == 'continuation':
            head = '- Thread `{}`: continuation reply, resolve no'.format(action.get('thread_id'))
        else:
            head = '- Thread `{}`: reply, resolve {}'.format(action.get('thread_id'),
                                                            'yes' if action.get('resolve') else 'no')
        out += [head, '', _quote(action.get('reply_body') or ''), '']
    if lint:
        out += ['## Remaining check findings', '']
        out += ['- [{}] {}: {}'.format(f.get('rule'), f.get('location'), f.get('message')) for f in lint]
        out.append('')
    return out


def cmd_preview(args):
    draft = Path(args.draft)
    lint = _load(draft / 'lint.json', [])
    if not (draft / 'payload.json').exists():
        # Thread actions without a review (no review is posted for the PR):
        # the preview shows the thread actions the approval binds
        if not (draft / 'thread-actions.json').exists():
            raise UsageError(str(draft) + ' has neither payload.json nor thread-actions.json')
        actions = validate_actions(_load(draft / 'thread-actions.json'))
        out = ['# Review preview', '',
               '- Review type: none; no review will be posted, only the thread actions below',
               '- Proposed thread actions: {}'.format(len(actions)), '']
        path = draft / 'preview.md'
        _write(path, '\n'.join(out + _preview_tail(actions, lint)))
        print(path)
        return 0
    payload = _load(draft / 'payload.json')
    actions = validate_actions(_load(draft / 'thread-actions.json', []))
    meta = _load(draft / 'draft.json', {})
    summary_only = meta.get('summary_only', []) if isinstance(meta, dict) else []
    kind = {'COMMENT': 'plain comment', 'REQUEST_CHANGES': 'request for changes'}.get(
        payload.get('event'), 'unsupported review type {}'.format(json.dumps(payload.get('event'))))
    comments = payload.get('comments') or []
    out = ['# Review preview', '',
           '- Review type: ' + kind,
           '- Pinned commit: ' + ('`{}`'.format(payload['commit_id']) if payload.get('commit_id') else 'missing'),
           '- Inline comments: {}'.format(len(comments)),
           '- Findings in the summary only: {}'.format(len(summary_only)),
           '', '## Summary body', '', '---', '', payload.get('body', ''), '', '---', '',
           '## Inline comments', '']
    if not comments:
        out += ['None.', '']
    for comment in comments:
        where = ('{}:{}-{}'.format(comment['path'], comment['start_line'], comment['line'])
                 if comment.get('start_line') else '{}:{}'.format(comment['path'], comment['line']))
        out += ['### `{}`'.format(where), '', comment.get('body', ''), '']
    out += ['## Findings in the summary only', '']
    if not summary_only:
        out += ['None.', '']
    for item in summary_only:
        out.append('- **{}** `{}`: {} Reason: {}'.format(
            item.get('severity'), _where(item),
            _text(item.get('description')), _text(item.get('reason')) or 'no reason recorded'))
    if summary_only:
        out.append('')
    out += _preview_tail(actions, lint)
    path = draft / 'preview.md'
    _write(path, '\n'.join(out))
    print(path)
    return 0


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------

def _without_fences(text):
    lines, fence = [], None
    for line in text.splitlines():
        boundary = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if boundary:
            token, rest = boundary.groups()
            if fence is None:
                fence = token[0], len(token)
                lines.append('')
                continue
            if token[0] == fence[0] and len(token) >= fence[1] and not rest.strip():
                fence = None
                lines.append('')
                continue
        lines.append('' if fence else line)
    return '\n'.join(lines)


def prose(text):
    """Text outside code, URLs, HTML comments and path-like tokens."""
    text = _without_fences(text)
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.S)
    text = re.sub(r'(`+)(?:(?!\1).)+?\1', 'x', text, flags=re.S)
    text = re.sub(r'https?://\S+', 'x', text)
    text = re.sub(r'\S*/\S*', 'x', text)
    text = re.sub(r'\b[\w-]+(?:\.[\w-]+)*\.[a-z][a-z0-9]{0,6}\b', 'x', text)
    return text


def _sections(body):
    """Heading -> content lines, headings scanned outside fenced code."""
    lines = _without_fences(body).splitlines()
    raw = body.splitlines()
    sections, order, current = {}, [], None
    for i, line in enumerate(lines):
        if re.match(r'^#{1,6} ', line):
            current = line.strip()
            order.append(current)
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(raw[i])
    return order, sections


def _structure(body):
    """Problems of one inline comment body (labels in order, footer last)."""
    lines = body.splitlines()
    problems = []

    def first(pattern):
        for i, line in enumerate(lines):
            if re.match(pattern, line):
                return i
        return None

    severity = first(r'^\*\*(?:{})\*\*: \S'.format('|'.join(SEVERITIES)))
    why = first(r'^\*\*Why this matters\*\*: \S')
    fix = first(r'^\*\*Suggested fix\*\*: \S')
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    source = nonempty[-1] if nonempty and re.match(r'^_Source: .+_$', lines[nonempty[-1]]) else None
    if severity != 0:
        problems.append('does not start with a severity label and text')
    if why is None:
        problems.append('"Why this matters" label missing or empty')
    if fix is None:
        problems.append('"Suggested fix" label missing or empty')
    if source is None:
        problems.append('source footer missing or not last')
    found = [i for i in (severity, why, fix, source) if i is not None]
    if found != sorted(found):
        problems.append('labels out of order')
    return problems


def _claim_text(text):
    """Typographic apostrophes as plain ones, so "I’ve tested" is a claim too."""
    return text.replace('’', "'").replace('‘', "'")


def _prose_rules(add, where, text):
    """The dash and missing-space rules (FR-012) on the prose of one text."""
    clean = prose(text)
    if '\u2014' in clean or '\u2013' in clean:
        add('dash', where, 'em or en dash in prose')
    for match in re.finditer(r'[.!?][A-Z]', clean):
        add('spacing', where, 'sentence end without a space before "{}"'.format(match.group(0)))


def _claim_rules(add, facts, claim_texts, result_texts):
    """The first-person claim rule (FR-011) and the test result rule (FR-009)."""
    allowed = set()
    if facts['curated']:
        allowed |= CURATION_VERBS
    if _ran(facts):
        allowed |= EXECUTION_VERBS
    for where, text in claim_texts:
        for match in CLAIM.finditer(prose(_claim_text(text))):
            if match.group(1) not in allowed:
                add('claim', where, 'unsupported first-person claim "{}"'.format(match.group(0)))
    # A passing result needs a passing latest round: a recorded failure does
    # not back "tests pass" (FR-009). A named command must be one the latest
    # round ran with the outcome passed.
    for where, text in result_texts:
        plain = re.sub(r'<!--.*?-->', ' ', _claim_text(text), flags=re.S).replace('`', '')
        plain = _without_agent_reports(plain)
        claims, rest = _named_results(plain, facts)
        # "did not pass" or "fails to pass" reports a failure, not a pass
        unbacked = next((phrase for phrase, command in claims
                         if not NEGATION.search(phrase) and not _passed_command(facts, command)), None)
        if unbacked:
            add('result', where, 'test result "{}" without {}'.format(
                unbacked, 'a passing run of that command in the latest fix round' if _ran(facts)
                else 'a recorded test run'))
            continue
        if not _passed(facts):
            for pattern in RESULT_PATTERNS:
                match = next((m for m in pattern.finditer(rest) if not NEGATION.search(m.group(0))), None)
                if match:
                    add('result', where, 'test result "{}" without {}'.format(
                        match.group(0), 'a passing latest fix round' if _ran(facts) else 'a recorded test run'))
                    break


def lint(draft, facts, expected_head, run_marker):
    """Check findings of the draft: the review (payload.json, when the draft
    holds one) and the proposed thread actions. A draft of thread actions
    alone has no payload: only its thread-action text is checked."""
    draft = Path(draft)
    has_payload = (draft / 'payload.json').exists()
    if not has_payload and not (draft / 'thread-actions.json').exists():
        raise UsageError(str(draft) + ' has neither payload.json nor thread-actions.json')
    actions = validate_actions(_load(draft / 'thread-actions.json', []))
    findings = []

    def add(rule, location, message):
        findings.append(dict(rule=rule, location=location, message=message))

    if has_payload:
        _lint_review(draft, facts, expected_head, run_marker, add)
    # Every reply text gets the prose rules; the continuation responses are
    # generated text, so they also get the claim and result rules (FR-009 to
    # FR-011). A resolution reply states the verified outcome of
    # verification.json and is checked for prose only.
    for index, action in enumerate(actions, 1):
        where = _action_where(index, action)
        text = action.get('reply_body') or ''
        _prose_rules(add, where, text)
        if action_kind(action) in CONTINUATION_KINDS:
            _claim_rules(add, facts, [(where, text)], [(where, text)])
    return findings


def _lint_review(draft, facts, expected_head, run_marker, add):
    payload = _load(draft / 'payload.json')
    slots = _load(draft / 'slots.json', None)
    if not isinstance(payload, dict):
        raise UsageError('payload.json must be a JSON object')
    body = payload.get('body') if isinstance(payload.get('body'), str) else ''
    comments = payload.get('comments') if isinstance(payload.get('comments'), list) else []

    marker = '<!-- cc-review:run-id:{} -->'.format(run_marker)
    if marker not in [line.strip() for line in body.splitlines()]:
        add('marker', 'summary body', 'run marker line {} is missing'.format(marker))
    if payload.get('event') not in EVENTS:
        add('event', 'payload', 'review type {} is not COMMENT or REQUEST_CHANGES'.format(
            json.dumps(payload.get('event'))))
    commit = payload.get('commit_id')
    if not commit:
        add('commit', 'payload', 'no pinned commit; the review cannot be posted')
    elif commit != expected_head:
        add('commit', 'payload', 'pinned commit {} differs from the expected head {}'.format(commit, expected_head))

    for index, comment in enumerate(comments, 1):
        where = 'comment {} ({}:{})'.format(index, comment.get('path'), comment.get('line'))
        for problem in _structure(comment.get('body') or ''):
            add('comment-structure', where, problem)

    order, sections = _sections(body)
    if not body.startswith('## cc-review Summary'):
        add('summary-order', 'summary body', 'the body does not start with "## cc-review Summary"')
    for heading in REQUIRED_SECTIONS:
        if heading not in order:
            add('summary-order', 'summary body', 'section "{}" is missing'.format(heading))
    for heading in sorted(set(order)):
        if order.count(heading) > 1:
            add('summary-order', 'summary body', 'section "{}" appears more than once'.format(heading))
        if heading not in SECTION_ORDER:
            add('summary-order', 'summary body', 'unexpected section "{}"'.format(heading))
    ranks = [SECTION_ORDER.index(h) for h in order if h in SECTION_ORDER]
    if ranks != sorted(ranks):
        add('summary-order', 'summary body', 'sections are out of order')

    details = [line.strip() for line in sections.get('### Review Details', []) if line.strip()]
    first_line = details[0] if details else ''
    if isinstance(slots, dict):
        expected = _text(slots.get('attribution_override')) or attribution(facts, bool(slots.get('repro_present')))
    else:
        expected = None
    body_lines = [line.strip() for line in body.splitlines()]
    lead_lines = [i for i, line in enumerate(body_lines) if line.startswith(ATTRIBUTION_LEADS)]
    if expected is not None:
        occurrences = body.count(expected)
        if occurrences == 0:
            add('attribution', 'Review Details', 'the attribution statement is missing')
        elif occurrences > 1 or len([i for i in lead_lines if body_lines[i] != expected]) > 0:
            add('attribution', 'Review Details', 'the attribution statement appears more than once')
        if occurrences and first_line != expected:
            add('attribution', 'Review Details', 'the attribution statement is not the first line of Review Details')
    else:
        if not lead_lines:
            add('attribution', 'Review Details', 'the attribution statement is missing')
        elif len(lead_lines) > 1:
            add('attribution', 'Review Details', 'the attribution statement appears more than once')
        if lead_lines and not first_line.startswith(ATTRIBUTION_LEADS):
            add('attribution', 'Review Details', 'the attribution statement is not the first line of Review Details')

    texts = [('summary body', body)] + [
        ('comment {} ({}:{})'.format(i, c.get('path'), c.get('line')), c.get('body') or '')
        for i, c in enumerate(comments, 1)]
    for where, text in texts:
        _prose_rules(add, where, text)

    generated = [('Follow-up progress', '\n'.join(sections.get('### Follow-up progress', []))),
                 ('What Went Well', '\n'.join(sections.get('### What Went Well', [])))]
    # A hand-written attribution replaces the generated statement: it gets the
    # claim and result rules of generated text, wherever it ended up
    override = _text(slots.get('attribution_override')) if isinstance(slots, dict) else ''
    claim_texts = generated + [('Review Details', first_line)]
    result_texts = list(generated)
    if override:
        if override != first_line:
            claim_texts.append(('attribution override', override))
        result_texts.append(('attribution override', override))
    _claim_rules(add, facts, claim_texts, result_texts)


def cmd_lint(args):
    draft = Path(args.draft)
    findings = lint(draft, load_facts(args.facts), args.expected_head, args.run_marker)
    _write_json(draft / 'lint.json', findings)
    if args.count_attempt and (draft / 'draft.json').exists():
        meta = _load(draft / 'draft.json')
        if isinstance(meta, dict):
            meta['lint_attempts'] = (meta.get('lint_attempts') if _int(meta.get('lint_attempts')) else 0) + 1
            _write_json(draft / 'draft.json', meta)
    print('LINT ok' if not findings else 'LINT findings={}'.format(len(findings)))
    return 1 if findings else 0


# ---------------------------------------------------------------------------
# Conversation check
# ---------------------------------------------------------------------------

# Local clocks and GitHub's may differ: an item counts as created after the
# analysis only when it is younger than the analysis time minus this margin
CLOCK_SKEW = datetime.timedelta(minutes=5)
ANALYZED_AT_FILE = 'analyzed-at.json'


def _actor(item):
    actor = item.get('author') if isinstance(item, dict) else None
    if isinstance(actor, dict):
        return actor.get('login') or '', actor.get('__typename') == 'Bot' or actor.get('type') == 'Bot'
    return (actor if isinstance(actor, str) else ''), False


def _time(value):
    """An ISO 8601 timestamp as an aware datetime, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=datetime.timezone.utc)


def _created(item):
    return _time(item.get('createdAt') or item.get('submittedAt'))


def _item(kind, data):
    login, bot = _actor(data)
    return dict(kind=kind, login=login, bot=bot, created=_created(data))


def analyzed_at(directory):
    """The analysis time recorded in the scope directory, or None."""
    value = _load(Path(directory) / ANALYZED_AT_FILE, None)
    return _time(value.get('analyzed_at')) if isinstance(value, dict) else None


def conversation_items(directory, required):
    """Item id -> {kind, login, bot, created} of a conversation snapshot."""
    directory = Path(directory)
    items = {}

    def collection(name):
        default = _MISSING if required else []
        value = _load(directory / name, default)
        if not isinstance(value, list):
            raise UsageError(str(directory / name) + ' must be a JSON array')
        return value

    for thread in collection('threads.json'):
        nodes = ((thread or {}).get('comments') or {}).get('nodes') or []
        for position, node in enumerate(nodes):
            if isinstance(node, dict) and node.get('id'):
                items[str(node['id'])] = _item('thread' if position == 0 else 'review-comment', node)
    for comment in collection('comments.json'):
        if isinstance(comment, dict) and (comment.get('id') or comment.get('databaseId')):
            items[str(comment.get('id') or comment.get('databaseId'))] = _item('comment', comment)
    for review in collection('reviews.json'):
        if isinstance(review, dict) and (review.get('databaseId') or review.get('id')):
            items[str(review.get('databaseId') or review.get('id'))] = _item('review', review)
    return items


def new_items(before, now, user, ignored=(), since=None):
    """Items of `now` that count as a conversation change (FR-021(c)).

    An item counts when someone other than the user wrote it (bots and
    ignored authors are treated alike), it is not part of `before`, and, when
    the analysis time `since` is known and the item has a creation time, it
    was created after the analysis. Edits never count: an edited item keeps
    its id and creation time.
    """
    ignored = set(ignored)
    cutoff = since - CLOCK_SKEW if since else None
    new = []
    for ident, item in now.items():
        login = item['login']
        if (ident in before or login == user or item['bot'] or login.endswith('[bot]')
                or login in ignored):
            continue
        if cutoff and item['created'] and item['created'] <= cutoff:
            continue
        new.append(dict(kind=item['kind'], id=ident, author=login))
    return sorted(new, key=lambda entry: (entry['kind'], entry['id']))


def conversation_diff(analysis, current, user, ignored=()):
    # Node ids are unique: compare by id alone, so a reply that becomes the
    # first comment of its thread (its root was deleted) is not new
    before = set(conversation_items(analysis, required=False))
    now = conversation_items(current, required=True)
    return new_items(before, now, user, ignored, analyzed_at(analysis))


def cmd_conversation_diff(args):
    new = conversation_diff(args.analysis, args.current, args.user, args.ignore_author or ())
    print(json.dumps(new, sort_keys=True))
    return 1 if new else 0


def history_items(history):
    """Item id -> {kind, login, bot, created} of a Follow-up Continuity history."""
    if not isinstance(history, dict):
        raise UsageError('a history must be a JSON object')
    items = {}
    for source in history.get('sources') or []:
        data = source.get('data') if isinstance(source, dict) else None
        if not isinstance(data, dict):
            continue
        kind = source.get('kind')
        if kind == 'thread':
            nodes = (data.get('comments') or {}).get('nodes') or []
            for position, node in enumerate(nodes):
                if isinstance(node, dict) and node.get('id'):
                    items[str(node['id'])] = _item('thread' if position == 0 else 'review-comment', node)
        elif data.get('databaseId') or data.get('id'):
            first, second = ('databaseId', 'id') if kind == 'review' else ('id', 'databaseId')
            ident = str(data.get(first) or data.get(second))
            items[ident] = _item(kind or 'source', data)
    for comment in history.get('context_comments') or []:
        if isinstance(comment, dict) and (comment.get('id') or comment.get('databaseId')):
            items[str(comment.get('id') or comment.get('databaseId'))] = _item('comment', comment)
    return items


def cmd_history_diff(args):
    before = history_items(_load(args.analysis_history))
    now = history_items(_load(args.current_history))
    new = new_items(set(before), now, args.user, args.ignore_author or (), analyzed_at(args.scope))
    print(json.dumps(new, sort_keys=True))
    return 1 if new else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parser():
    root = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = root.add_subparsers(dest='command', required=True)

    p = sub.add_parser('facts-set', help='record a run fact')
    p.add_argument('--facts', required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--curated', choices=('true', 'false'))
    group.add_argument('--executed')
    p.set_defaults(func=cmd_facts_set)

    p = sub.add_parser('assemble', help='build payload.json from slots and facts')
    p.add_argument('--slots', required=True)
    p.add_argument('--facts', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--inputs-key', required=True)
    p.add_argument('--max-comments', type=int)
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser('attribution', help='print the attribution statement')
    p.add_argument('--facts', required=True)
    p.add_argument('--repro', action='store_true')
    p.set_defaults(func=cmd_attribution)

    p = sub.add_parser('preview', help='render preview.md')
    p.add_argument('--draft', required=True)
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser('lint', help='check the assembled draft')
    p.add_argument('--draft', required=True)
    p.add_argument('--facts', required=True)
    p.add_argument('--expected-head', required=True)
    p.add_argument('--run-marker', required=True)
    p.add_argument('--count-attempt', action='store_true')
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser('fingerprint', help='fingerprint payload.json and thread-actions.json')
    p.add_argument('--draft', required=True)
    p.set_defaults(func=cmd_fingerprint)

    p = sub.add_parser('conversation-diff', help='new non-bot conversation items since analysis')
    p.add_argument('--analysis', required=True)
    p.add_argument('--current', required=True)
    p.add_argument('--user', required=True)
    p.add_argument('--ignore-author', action='append', help='a login treated like a bot (repeatable)')
    p.set_defaults(func=cmd_conversation_diff)

    p = sub.add_parser('history-diff', help='new history items by other people since analysis')
    p.add_argument('--analysis-history', required=True)
    p.add_argument('--current-history', required=True)
    p.add_argument('--scope', required=True, help='scope directory with analyzed-at.json')
    p.add_argument('--user', required=True)
    p.add_argument('--ignore-author', action='append', help='a login treated like a bot (repeatable)')
    p.set_defaults(func=cmd_history_diff)

    p = sub.add_parser('inputs-key', help='hash of the draft inputs')
    p.add_argument('--expected-head', required=True)
    p.add_argument('--findings', required=True)
    p.add_argument('--facts', required=True)
    p.set_defaults(func=cmd_inputs_key)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except UsageError as error:
        print('Error: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
