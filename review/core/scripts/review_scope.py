#!/usr/bin/env python3
"""Personal review coverage, contribution scope and evidence-backed verification.

No network or hosting mutations. Git comparisons use a disposable index and
never change the invoking checkout, index, refs or branch.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import reviewer_activity as activity

OID = re.compile(r'[0-9a-f]{40}(?:[0-9a-f]{24})?\Z')
KEY = re.compile(r'[0-9a-f]{64}\Z')
RUN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,255}\Z')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _identity(value):
    activity._identity(value)
    return value


def coverage_key(reviewers, settings, context_files):
    """Fingerprint effective coverage, independent of run-local file paths."""
    entries = []
    for reviewer in reviewers:
        if reviewer.get('status') not in ('ready', 'dispatched', 'ok'):
            continue
        entry = {k: reviewer.get(k) for k in ('name', 'kind', 'command', 'requires', 'category',
                                             'context', 'severity_map', 'dedup')}
        if isinstance(entry['command'], dict):
            entry['command'] = json.loads(_json(entry['command']))
            output = entry['command'].get('output')
            if isinstance(output, dict):
                parser_path = output.pop('parser_path', None)
                if parser_path:
                    entry['parser_content'] = hashlib.sha256(Path(parser_path).read_bytes()).hexdigest()
        paths = [reviewer['body_file']] if reviewer.get('body_file') else []
        paths += reviewer.get('references', reviewer.get('reference_files', []))
        entry['content'] = [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths]
        entries.append(entry)
    context = [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in context_files]
    value = dict(version=1, reviewers=sorted(entries, key=lambda e: e['name']),
                 settings=settings, context=context)
    return hashlib.sha256(_json(value).encode()).hexdigest()


def parse_completion(review, identity):
    """A marker is evidence only in its owner's submitted review at that head."""
    if not isinstance(review, dict) or activity.author(review) != identity['user']:
        return None
    if review.get('state') not in ('COMMENTED', 'APPROVED', 'CHANGES_REQUESTED', 'DISMISSED'):
        return None
    body = activity._without_fenced_code(review.get('body') or '')
    if re.search(r'^<!-- cc-review-incomplete:v1 -->$', body, re.M):
        return None
    markers = re.findall(r'^<!-- cc-review-scope:v1 (\{[^\n]{1,8192}\}) -->$', body, re.M)
    runs = re.findall(r'^<!-- cc-review:run-id:([^\s<>]{1,256}) -->$', body, re.M)
    if len(markers) != 1 or len(runs) != 1:
        return None
    try:
        value = json.loads(markers[0])
        if (not isinstance(value, dict) or value.get('identity') != identity
                or value.get('complete') is not True or value.get('run_id') != runs[0]
                or not RUN.fullmatch(value['run_id'])
                or value.get('mode') not in ('full', 'incremental', 'unchanged')
                or not OID.fullmatch(value.get('head_oid', ''))
                or not OID.fullmatch(value.get('base_oid', ''))
                or not KEY.fullmatch(value.get('coverage_key', ''))
                or (review.get('commit') or {}).get('oid') != value['head_oid']
                or not RUN.fullmatch(value.get('root_run_id', ''))):
            return None
        parent = value.get('parent_run_id')
        if value['mode'] == 'full':
            if parent is not None or value['root_run_id'] != value['run_id']:
                return None
        elif not isinstance(parent, str) or not RUN.fullmatch(parent):
            return None
        return value
    except (ValueError, KeyError, TypeError):
        return None


def select_baseline(snapshot):
    if snapshot.get('reviews_complete') is not True:
        return None, 'Review history is incomplete'
    entries, duplicate = {}, set()
    for index, review in enumerate(snapshot.get('reviews', [])):
        value = parse_completion(review, snapshot['identity'])
        if value:
            run = value['run_id']
            if run in entries:
                duplicate.add(run)
            entries[run] = (value, review.get('submittedAt') or '', index)
    def rooted(value):
        seen = set()
        root = value['root_run_id']
        while value['run_id'] not in seen:
            run = value['run_id']
            if run in duplicate or value['coverage_key'] != snapshot['coverage_key']:
                return False
            seen.add(run)
            if value['mode'] == 'full':
                return run == root
            parent = entries.get(value['parent_run_id'])
            if not parent or parent[0]['root_run_id'] != root:
                return False
            value = parent[0]
        return False
    candidates = sorted(entries.values(), key=lambda e: (e[1], e[2]), reverse=True)
    if not candidates:
        return None, 'No trustworthy completed personal review baseline'
    latest = candidates[0][0]
    if latest['coverage_key'] != snapshot['coverage_key']:
        return None, 'Effective reviewer coverage or settings changed'
    if not rooted(latest):
        return None, 'Completed coverage chain is missing, incompatible or cyclic'
    return latest, 'Latest completed personal review'


def _git(repo, *args, data=None, env=None):
    variables = dict(os.environ)
    variables['GIT_OPTIONAL_LOCKS'] = '0'
    # Never let an inherited temporary index redirect the real comparison.
    variables.pop('GIT_INDEX_FILE', None)
    if env:
        variables.update(env)
    command = ['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null', *args]
    result = subprocess.run(command, input=data, capture_output=True, env=variables, timeout=60)
    if result.returncode:
        raise ValueError('Git comparison unavailable: ' + result.stderr.decode(errors='replace')[:300].strip())
    return result.stdout


def _commit(repo, ref):
    if not isinstance(ref, str) or not ref or ref.startswith('-'):
        raise ValueError('Invalid commit reference')
    return _git(repo, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()


def _diff(repo, before, head):
    diff = _git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--binary', '--full-index',
                '--find-renames', before, head, '--').decode(errors='replace')
    tokens = _git(repo, 'diff', '--name-status', '-z', '--find-renames', before, head, '--').split(b'\0')
    changes, i = {}, 0
    while i < len(tokens) and tokens[i]:
        status = tokens[i].decode('ascii')
        i += 1
        paths = [os.fsdecode(tokens[i])]
        i += 1
        if status.startswith(('R', 'C')):
            paths.append(os.fsdecode(tokens[i]))
            i += 1
        patch = _git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--unified=0',
                     '--find-renames', before, head, '--', *paths).decode(errors='replace')
        ranges = []
        for start, count in re.findall(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', patch, re.M):
            first, length = max(1, int(start)), int(count) if count else 1
            ranges.append([first, first + max(length, 1) - 1])
        if status == 'D':
            # Removed files have no current lines. Keep their old changed
            # coordinates so deletion findings survive as summary-only items.
            ranges = [[int(start), int(start) + (int(count) if count else 1) - 1]
                      for start, count in re.findall(r'^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@', patch, re.M)]
        changes[paths[-1]] = ranges
        if len(paths) > 1:
            changes[paths[0]] = []
    return diff, changes


def plan_scope(repo, snapshot):
    _identity(snapshot.get('identity'))
    if not isinstance(snapshot.get('coverage_key'), str) or not KEY.fullmatch(snapshot['coverage_key']):
        raise ValueError('coverage_key must be a SHA-256 fingerprint')
    repo = Path(repo)
    head = _commit(repo, snapshot.get('head_oid'))
    base_tip = _commit(repo, snapshot.get('base_oid'))
    bases = _git(repo, 'merge-base', '--all', base_tip, head).decode().split()
    if len(bases) != 1:
        raise ValueError('Current PR has no unique merge-base; review inputs incomplete')
    base = bases[0]
    clean = (not _git(repo, 'status', '--porcelain', '--untracked-files=no').strip()
             and _commit(repo, 'HEAD') == head)
    baseline, reason = select_baseline(snapshot)
    result = dict(mode='full', identity=snapshot['identity'], head_oid=head, base_oid=base,
                  coverage_key=snapshot['coverage_key'], baseline=None, reason=reason,
                  complete=clean, clean=clean, review_required=True, acknowledgment_required=False,
                  required_reviewers=snapshot.get('required_reviewers', []))
    before = base
    if snapshot.get('full'):
        result['reason'] = 'Explicit --full override'
    elif not clean:
        result['reason'] = 'Dirty or unpinned checkout; full local review without completed baseline'
    elif baseline:
        try:
            old_head = _commit(repo, baseline['head_oid'])
            old_base = _commit(repo, baseline['base_oid'])
            ancestor = subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', old_head, head],
                                      capture_output=True, timeout=60).returncode == 0
            if old_base == base and ancestor:
                before = old_head
            else:
                patch = _git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--binary', '--full-index', old_base, old_head, '--')
                with tempfile.TemporaryDirectory(prefix='cc-review-index-') as temp:
                    env = {'GIT_INDEX_FILE': str(Path(temp) / 'index')}
                    _git(repo, 'read-tree', base, env=env)
                    if patch:
                        _git(repo, 'apply', '--cached', '--3way', '--whitespace=nowarn', data=patch, env=env)
                    before = _git(repo, 'write-tree', env=env).decode().strip()
            result.update(mode='incremental', baseline=baseline, reason=reason)
        except (ValueError, subprocess.TimeoutExpired) as error:
            before = base
            result['reason'] = 'Full fallback: ' + str(error)
    diff, changes = _diff(repo, before, head)
    if result['mode'] == 'incremental' and not diff:
        result.update(mode='unchanged', review_required=False,
                      acknowledgment_required=snapshot.get('renewed_request') is True,
                      reason='Author contribution is unchanged; thread verification remains independent')
    result.update(diff=diff, changes=changes)
    return result


def verification_targets(snapshot):
    identity = _identity(snapshot.get('identity'))
    head = snapshot.get('head_oid')
    if not isinstance(head, str) or not OID.fullmatch(head):
        raise ValueError('Verification requires a pinned head object ID')
    targets, warnings, seen = [], [], set()
    if snapshot.get('threads_complete') is not True:
        warnings.append('Thread collection is incomplete')
    threads = snapshot.get('threads')
    if not isinstance(threads, list):
        raise ValueError('threads must be a complete collection array')
    for thread in threads:
        activity.validate_thread(thread)
        root = activity.root_comment(thread)
        if thread.get('isResolved') is True:
            continue
        if not root:
            warnings.append('Thread root unavailable')
            continue
        if activity.author(root) == identity['user'] and not isinstance(root.get('body'), str):
            warnings.append('Owned root content is unavailable')
            continue
        if not activity.owned_root(root, identity['user']):
            continue
        current = activity.fingerprint(thread, head, identity['user'], identity)
        if not current or thread.get('isResolved') is not False or thread.get('id') in seen:
            warnings.append('Owned thread has missing, duplicate or incomplete evidence')
            continue
        seen.add(thread['id'])
        targets.append(dict(thread_id=thread['id'], root_comment_id=root['id'],
                            concern=root['body'], activity=current))
    return dict(complete=not warnings, identity=identity, head_oid=head, targets=targets, warnings=warnings)


def reconcile_verifications(batch, outcomes):
    """Reconcile explicit code checks, never rediscovery or line proximity."""
    warnings = list(batch.get('warnings') or [])
    if batch.get('complete') is not True:
        warnings.append('Verification targets are incomplete')
    verified, resolutions = [], []
    groups = {}
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            warnings.append('Malformed verification outcome')
            continue
        tid = (outcome.get('activity') or {}).get('thread_id')
        groups.setdefault(tid, []).append(outcome)
    targets = batch.get('targets', [])
    for target in targets:
        tid = target['thread_id']
        matches = groups.pop(tid, [])
        if len(matches) != 1:
            warnings.append('Missing or duplicate verification: ' + tid)
            continue
        outcome = matches[0]
        status = outcome.get('status')
        if (outcome.get('activity') != target['activity']
                or outcome.get('code_checked') is not True
                or not isinstance(outcome.get('evidence'), str) or not outcome['evidence'].strip()
                or status not in ('confirmed-fixed', 'still-present', 'accepted-explanation')
                or (status == 'accepted-explanation' and outcome.get('approved') is not True)):
            warnings.append('Stale, unclear or unsupported verification: ' + tid)
            continue
        if status == 'still-present':
            finding = outcome.get('finding')
            if (not isinstance(finding, dict) or finding.get('severity') not in ('Critical', 'Important', 'Minor', 'Notable')
                    or not isinstance(finding.get('file'), str) or not finding['file']
                    or type(finding.get('line_start')) is not int or finding['line_start'] < 1):
                warnings.append('Still-present concern lacks a normalized carried finding: ' + tid)
                continue
        verified.append(dict(outcome, thread_id=tid))
        if status in ('confirmed-fixed', 'accepted-explanation'):
            resolutions.append(tid)
    if groups:
        warnings.append('Verification contains unknown threads')
    return dict(complete=not warnings, identity=batch.get('identity'), head_oid=batch.get('head_oid'),
                verified=verified, resolutions=resolutions, warnings=warnings)


def filter_findings(scope, findings, verified):
    """One finding policy for prompt/command reviewers and all pipeline stages."""
    accepted, excluded = [], []
    carried = {v.get('thread_id') for v in verified if v.get('status') == 'still-present'
               and v.get('code_checked') is True and v.get('evidence')
               and (v.get('activity') or {}).get('head_oid') == scope.get('head_oid')}
    # The explicit code check preserves concerns a new reviewer did not
    # rediscover. Its normalized concern is authoritative for carried items.
    canonical = {v['thread_id']: dict(v['finding'], prior_thread_id=v['thread_id'])
                 for v in verified if v.get('thread_id') in carried and isinstance(v.get('finding'), dict)}
    candidates = list(canonical.values()) + [f for f in findings if f.get('prior_thread_id') not in canonical]
    for finding in candidates:
        path, line = finding.get('file'), finding.get('line_start')
        if (not isinstance(path, str) or not path or path.startswith('/')
                or '..' in path.split('/') or type(line) is not int or line < 1):
            excluded.append(dict(finding=finding, reason='Invalid location'))
            continue
        prior = finding.get('prior_thread_id')
        if prior:
            if prior in carried:
                accepted.append(dict(finding, scope='carried'))
            else:
                excluded.append(dict(finding=finding, reason='Prior thread lacks exact verification'))
            continue
        end = finding.get('line_end', line)
        if type(end) is not int or end < line:
            excluded.append(dict(finding=finding, reason='Invalid line range'))
            continue
        intersects = any(start <= end and stop >= line for start, stop in scope.get('changes', {}).get(path, []))
        if scope.get('mode') == 'full' or intersects:
            accepted.append(dict(finding, scope='latest_delta'))
        elif finding.get('severity') == 'Critical' and isinstance(finding.get('evidence'), str) and finding['evidence'].strip():
            accepted.append(dict(finding, scope='unchanged_critical'))
        else:
            excluded.append(dict(finding=finding, reason='Outside delta without evidenced critical exception'))
    return dict(findings=accepted, excluded=excluded)


def completion_marker(scope, run_id, reviewers, verification):
    _identity(scope.get('identity'))
    if not isinstance(run_id, str) or not RUN.fullmatch(run_id):
        raise ValueError('Invalid review run ID')
    reasons = []
    if scope.get('complete') is not True or scope.get('clean') is not True:
        reasons.append('Scope or pinned checkout is incomplete')
    if (verification.get('complete') is not True
            or verification.get('identity') != scope.get('identity')
            or verification.get('head_oid') != scope.get('head_oid')):
        reasons.append('Prior-finding verification is incomplete')
    required = [r for r in reviewers if r.get('required') is True]
    names = [r.get('name') for r in required]
    expected = scope.get('required_reviewers')
    if scope.get('mode') != 'unchanged' and (not isinstance(expected, list)
            or not expected or any(not isinstance(name, str) or not name for name in expected)
            or len(names) != len(set(names)) or set(names) != set(expected)):
        reasons.append('Required reviewer result set is missing, duplicate or mismatched')
    if scope.get('mode') != 'unchanged' and not required:
        reasons.append('Required reviewer coverage is missing')
    if any(r.get('status') != 'ok' or r.get('actual_scope') not in ('delta', 'full') for r in required):
        reasons.append('Required reviewer failed or actual scope is unavailable')
    if scope.get('mode') == 'full' and any(r.get('actual_scope') != 'full' for r in required):
        reasons.append('Full baseline requires full reviewer coverage')
    mode = scope.get('mode')
    baseline = scope.get('baseline')
    if mode not in ('full', 'incremental', 'unchanged') or (mode != 'full' and not baseline):
        reasons.append('Completed baseline chain unavailable')
    if reasons:
        return dict(complete=False, marker='', reasons=reasons)
    evidence = {key: scope[key] for key in ('identity', 'head_oid', 'base_oid', 'coverage_key')}
    evidence.update(run_id=run_id, mode=mode, complete=True,
                    parent_run_id=baseline['run_id'] if mode != 'full' else None,
                    root_run_id=baseline['root_run_id'] if mode != 'full' else run_id)
    review = dict(author={'login': scope['identity']['user']}, state='COMMENTED',
                  commit={'oid': scope['head_oid']},
                  body='<!-- cc-review:run-id:' + run_id + ' -->\n<!-- cc-review-scope:v1 ' + _json(evidence) + ' -->')
    if parse_completion(review, scope['identity']) is None:
        raise ValueError('Invalid completion evidence')
    return dict(complete=True, evidence=evidence, marker='<!-- cc-review-scope:v1 ' + _json(evidence) + ' -->', reasons=[])


def refresh_completion(candidate, snapshot, outcomes):
    """Recheck prepared verification against freshly collected conversations."""
    scope = candidate['scope']
    if snapshot.get('identity') != scope.get('identity') or snapshot.get('head_oid') != scope.get('head_oid'):
        return dict(complete=False, marker='', reasons=['Publication identity or head changed'])
    targets = verification_targets(snapshot)
    resolved = {t.get('id') for t in snapshot['threads'] if t.get('isResolved') is True
                and activity.owned_root(activity.root_comment(t), scope['identity']['user'])}
    outcomes = [o for o in outcomes if (o.get('activity') or {}).get('thread_id') not in resolved]
    verification = reconcile_verifications(targets, outcomes)
    return completion_marker(scope, candidate['run_id'], candidate['reviewers'], verification)


def publication_marker(completion, identity, run_id, head_oid):
    """Validate a saved completion artifact against the actual posted identity."""
    _identity(identity)
    if completion.get('complete') is not True:
        return dict(complete=False, marker='<!-- cc-review-incomplete:v1 -->')
    marker = completion.get('marker')
    if not isinstance(marker, str):
        raise ValueError('Completion marker is missing')
    review = dict(author={'login': identity['user']}, state='COMMENTED', commit={'oid': head_oid},
                  body='<!-- cc-review:run-id:' + run_id + ' -->\n' + marker)
    evidence = parse_completion(review, identity)
    if evidence is None or evidence != completion.get('evidence'):
        raise ValueError('Completion artifact does not match the published PR, run or head')
    return dict(complete=True, marker=marker)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'targets', 'reconcile', 'filter', 'marker', 'coverage', 'publication', 'refresh'])
    parser.add_argument('--input', required=True)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        snapshot = json.loads(Path(args.input).read_text())
        if args.command == 'prepare':
            if not args.output:
                raise ValueError('prepare requires --output')
            result = plan_scope(Path(args.repo), snapshot)
            directory = Path(args.output)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / 'scope.json').write_text(_json(result) + '\n')
            (directory / 'review.diff').write_text(result['diff'])
            result = {k: v for k, v in result.items() if k != 'diff'}
        elif args.command == 'targets':
            result = verification_targets(snapshot)
        elif args.command == 'reconcile':
            result = reconcile_verifications(snapshot['batch'], snapshot['outcomes'])
        elif args.command == 'filter':
            result = filter_findings(snapshot['scope'], snapshot['findings'], snapshot['verified'])
        elif args.command == 'marker':
            result = completion_marker(snapshot['scope'], snapshot['run_id'], snapshot['reviewers'], snapshot['verification'])
        elif args.command == 'publication':
            result = publication_marker(snapshot['completion'], snapshot['identity'], snapshot['run_id'], snapshot['head_oid'])
        elif args.command == 'refresh':
            result = refresh_completion(snapshot['candidate'], snapshot['threads_snapshot'], snapshot['outcomes'])
        else:
            result = dict(coverage_key=coverage_key(snapshot['reviewers'], snapshot['settings'], snapshot['context_files']))
        print(_json(result))
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, 'Error: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
