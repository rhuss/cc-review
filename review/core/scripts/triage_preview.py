#!/usr/bin/env python3
"""Render a bulk triage plan as a reviewable preview and fingerprint it.

render writes triage-preview.md next to the plan: the commit that would be
pushed, every reply with its full text, the threads that would be resolved,
the grouped PR comment and the human comment replies. It mirrors what
bulk-apply.sh triage acts on, so the user sees every text before it is
posted under their name. fingerprint hashes the whole plan, so an approval
binds exactly the plan it was given for. Neither operation writes to GitHub.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

POSTABLE = ('confirmed-fixed', 'still-present', 'accepted-explanation')


class UsageError(Exception):
    pass


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise UsageError('{} not found'.format(path))
    except json.JSONDecodeError as exc:
        raise UsageError('{} is not valid JSON: {}'.format(path, exc))


def fingerprint(plan):
    data = json.dumps(plan, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def _quote(text):
    return '\n'.join('> ' + line if line else '>' for line in text.splitlines()) or '>'


def _link(identity, comment_id):
    if not isinstance(identity, dict) or type(comment_id) is not int:
        return None
    host, repo, pr = identity.get('host'), identity.get('repository'), identity.get('pr')
    if not (host and repo and pr):
        return None
    return 'https://{}/{}/pull/{}#discussion_r{}'.format(host, repo, pr, comment_id)


def _where(item):
    path = item.get('path')
    if not path:
        return None
    return '{}:{}'.format(path, item['line']) if item.get('line') is not None else path


def _git(worktree, *args):
    try:
        done = subprocess.run(['git', '-C', str(worktree)] + list(args), capture_output=True,
                              text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.rstrip('\n') if done.returncode == 0 else None


def _commit(sha, worktree):
    """Subject, body and file stat of the prepared commit, when readable."""
    if not worktree or not Path(worktree).is_dir():
        return None
    message = _git(worktree, 'log', '-1', '--format=%B', sha)
    stat = _git(worktree, 'show', '--stat', '--format=', sha)
    if message is None:
        return None
    return message.strip(), (stat or '').strip()


def _shown(body):
    """The reply as GitHub renders it: without the invisible run signature."""
    return re.sub(r'\s*<!-- cc-review-triage[^>]*-->', '', body or '').rstrip()


def author_items(plan, skip_accepted):
    """The replies bulk-apply.sh posts for an author plan, in its order."""
    items = []
    for item in plan.get('replies') or []:
        items.append(dict(item, kind='bot', action=item.get('action'), resolve=bool(item.get('resolve'))))
    for item in plan.get('cc_review_threads') or []:
        if item.get('body'):
            items.append(dict(item, kind='cc-review', action=item.get('action') or 'resolved',
                              resolve=bool(item.get('resolve'))))
    for item in plan.get('human') or []:
        if item.get('decision') in ('approve', 'edit'):
            body = item.get('body') or item.get('draft') or ''
            items.append(dict(item, kind='human', body=body, resolve=False,
                              action='edited' if item.get('decision') == 'edit' else 'approved'))
    posted, held = [], []
    for item in items:
        if not item.get('body'):
            held.append((item, 'no reply text'))
        elif skip_accepted and item.get('action') == 'accepted':
            held.append((item, 'fixes are not pushed (local branch has unpushed commits)'))
        else:
            posted.append(item)
    return posted, held


def reviewer_items(plan):
    """The reviewer actions of bulk-apply.sh: replies, resolutions, records."""
    summary = plan.get('resolution_summary') or {}
    summarized = set(summary.get('activity_keys') or [])
    posted, resolve_only, recorded, held = [], [], [], []
    for item in plan.get('cc_review_threads') or []:
        outcome = item.get('outcome') or {}
        key = (item.get('activity') or {}).get('activity_key')
        if key in summarized:
            continue
        if outcome.get('completed') is not True or outcome.get('status') not in POSTABLE:
            held.append((item, 'outcome {}: nothing is posted'.format(outcome.get('status') or 'unclear')))
            continue
        entry = dict(item, kind='cc-review', resolve=bool(item.get('resolve')),
                     action=outcome.get('status'))
        if item.get('body'):
            posted.append(entry)
        elif entry['resolve']:
            resolve_only.append(entry)
        else:
            recorded.append(entry)
    return posted, resolve_only, recorded, held


def _reply_block(index, item, identity):
    where = _where(item) or 'PR conversation'
    who = item.get('author') or 'unknown author'
    head = '### {}. `{}` · {} · {} · resolve {}'.format(
        index, where, who, item.get('action') or 'reply', 'yes' if item.get('resolve') else 'no')
    out = [head, '']
    link = _link(identity, item.get('comment_id'))
    if link:
        out += ['[Thread]({})'.format(link), '']
    if item.get('kind') == 'human' and item.get('text'):
        out += ['Their comment:', '', _quote(str(item['text'])), '', 'Your reply:', '']
    out += [_quote(_shown(item.get('body'))), '']
    return out


def render(plan, flags=(), worktree=None, role=None):
    role = role or plan.get('triage_role') or 'author'
    identity = plan.get('activity_identity')
    pr = plan.get('pr')
    out = ['# Triage preview: PR #{}'.format(pr), '']
    if role == 'reviewer':
        posted, resolve_only, recorded, held = reviewer_items(plan)
        summary = plan.get('resolution_summary')
        out += ['- Role: reviewer (verifies your own earlier findings; no code is pushed)',
                '- Thread replies: {} ({} also resolve the thread)'.format(
                    len(posted), sum(1 for i in posted if i['resolve'])),
                '- Threads resolved without a reply: {}'.format(len(resolve_only)),
                '- PR conversation comment: {}'.format(
                    '1, covering {} threads (the PR author must resolve them)'.format(
                        len(summary.get('activity_keys') or [])) if summary else 'none'),
                '- Outcomes recorded without posting: {}'.format(len(recorded)),
                '- Not acted on: {}'.format(len(held)), '']
        out += ['## Thread replies', '']
        if not posted:
            out += ['None.', '']
        for n, item in enumerate(posted, 1):
            out += _reply_block(n, item, identity)
        if resolve_only:
            out += ['## Threads resolved without a reply', '']
            for item in resolve_only:
                link = _link(identity, item.get('comment_id'))
                out.append('- `{}`{}'.format(item.get('thread_id'), ' ([thread]({}))'.format(link) if link else ''))
            out.append('')
        out += ['## PR conversation comment', '']
        if summary:
            out += ['---', '', _shown(summary.get('body')), '', '---', '']
        else:
            out += ['None.', '']
    else:
        skip_accepted = 'local-unpushed' in flags
        posted, held = author_items(plan, skip_accepted)
        prepared = plan.get('prepared_commit')
        stale = plan.get('stale_resolutions') or []
        if not prepared:
            push = 'none'
        elif skip_accepted:
            push = 'commit `{}` is NOT pushed: the local branch has unpushed commits'.format(prepared[:7])
        else:
            push = 'commit `{}`'.format(prepared[:7])
        humans = plan.get('human') or []
        out += ['- Role: author',
                '- Push: ' + push,
                '- Thread replies: {} ({} also resolve the thread)'.format(
                    len(posted), sum(1 for i in posted if i['resolve'])),
                '- Earlier handled threads resolved without a new reply: {}'.format(len(stale)),
                '- Human comments: {} approved, {} edited, {} skipped, {} undecided'.format(
                    sum(1 for h in humans if h.get('decision') == 'approve'),
                    sum(1 for h in humans if h.get('decision') == 'edit'),
                    sum(1 for h in humans if h.get('decision') == 'skip'),
                    sum(1 for h in humans if h.get('decision') is None)),
                '- Not posted: {}'.format(len(held)), '']
        if prepared:
            out += ['## Commit to push', '', '`{}`'.format(prepared), '']
            commit = _commit(prepared, worktree)
            if commit:
                message, stat = commit
                out += ['```text', message, '```', '']
                if stat:
                    out += ['```text', stat, '```', '']
            else:
                out += ['(commit details unavailable: the worktree is missing)', '']
        out += ['## Thread replies', '']
        if not posted:
            out += ['None.', '']
        for n, item in enumerate(posted, 1):
            out += _reply_block(n, item, identity)
        if stale:
            out += ['## Earlier handled threads resolved without a new reply', '']
            out += ['- `{}`'.format(t) for t in stale]
            out.append('')
    if held:
        out += ['## Not posted', '']
        for item, reason in held:
            out.append('- `{}` ({}): {}'.format(_where(item) or item.get('thread_id') or '?',
                                                item.get('author') or 'unknown author', reason))
        out.append('')
    return '\n'.join(out)


def cmd_render(args):
    plan_path = Path(args.plan)
    plan = _load(plan_path)
    flags = (args.flags or '').split()
    text = render(plan, flags=flags, worktree=args.worktree, role=args.role or None)
    out = Path(args.out) if args.out else plan_path.parent / 'triage-preview.md'
    out.write_text(text + '\n', encoding='utf-8')
    print(out)
    return 0


def cmd_fingerprint(args):
    print(fingerprint(_load(args.plan)))
    return 0


def main(argv=None):
    root = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = root.add_subparsers(dest='command', required=True)
    p = sub.add_parser('render', help='write triage-preview.md next to the plan')
    p.add_argument('--plan', required=True)
    p.add_argument('--role', help='trusted role from the bulk state (author or reviewer)')
    p.add_argument('--flags', help='space-separated PR flags from the bulk state')
    p.add_argument('--worktree', help='the PR worktree holding the prepared commit')
    p.add_argument('--out', help='output path (default: triage-preview.md next to the plan)')
    p.set_defaults(func=cmd_render)
    p = sub.add_parser('fingerprint', help='hash the plan an approval binds')
    p.add_argument('--plan', required=True)
    p.set_defaults(func=cmd_fingerprint)
    args = root.parse_args(argv)
    try:
        return args.func(args)
    except UsageError as exc:
        print('triage-preview: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
