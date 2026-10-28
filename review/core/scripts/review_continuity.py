#!/usr/bin/env python3
"""Read-only conversation history and evidence-backed follow-up conclusions.

Semantic judgments come from code-reading reviewers, never from keyword matching
of an author's explanation. This module checks their provenance and completeness.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

import reviewer_activity as activity


SUBMITTED = {'COMMENTED', 'APPROVED', 'CHANGES_REQUESTED', 'DISMISSED'}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def prepare_history(snapshot):
    """Preserve personal sources and contextual replies without claiming coverage."""
    identity = snapshot.get('identity')
    activity._identity(identity)
    head = snapshot.get('head_oid')
    if not isinstance(head, str) or not re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', head):
        raise ValueError('History requires a pinned head object ID')
    limitations, sources, seen = [], [], set()
    base = 'https://{host}/{repository}/pull/{pr}'.format(**identity)
    personal = False
    collections = {}
    for name in ('reviews', 'threads', 'comments'):
        value = snapshot.get(name)
        if not isinstance(value, list):
            limitations.append(name + ' collection is malformed')
            value = []
        collections[name] = value
        if snapshot.get(name + '_complete') is not True:
            limitations.append(name + ' collection is incomplete')

    def source(kind, data, anchor):
        sid = data.get('id') or data.get('databaseId')
        if not isinstance(sid, (str, int)) or isinstance(sid, bool) or not str(sid).strip():
            limitations.append(kind + ' source identity is missing')
            return
        key = kind + ':' + str(sid)
        if key in seen:
            limitations.append('Duplicate source identity: ' + key)
            return
        seen.add(key)
        sources.append(dict(source_id=key, kind=kind, url=data.get('url') or base + anchor,
                            data=copy.deepcopy(data)))

    for review in collections['reviews']:
        if not isinstance(review, dict):
            limitations.append('Malformed review')
            continue
        if review.get('state') not in SUBMITTED:
            continue
        if activity.author(review) != identity['user']:
            continue
        personal = True
        if not isinstance(review.get('body'), str):
            limitations.append('Personal review body is unavailable')
        source('review', review, '#pullrequestreview-' + str(review.get('databaseId', '')))

    for thread in collections['threads']:
        if not isinstance(thread, dict):
            limitations.append('Malformed thread')
            continue
        connection = thread.get('comments') or {}
        nodes = connection.get('nodes') if isinstance(connection, dict) else None
        if not isinstance(nodes, list) or not nodes:
            limitations.append('Thread conversation is unavailable')
            continue
        page = connection.get('pageInfo') or {}
        if (page.get('hasNextPage') is True or page.get('hasPreviousPage') is True
                or connection.get('totalCount', len(nodes)) != len(nodes)):
            limitations.append('Thread conversation is truncated')
        root = nodes[0]
        if not isinstance(root, dict) or activity.author(root) != identity['user']:
            continue
        parent_review = root.get('pullRequestReview') or {}
        if isinstance(parent_review, dict) and parent_review.get('state') == 'PENDING':
            continue
        personal = True
        if (thread.get('isResolved') not in (True, False)
                or any(not isinstance(c, dict) or not _text(c.get('id'))
                       or not isinstance(c.get('body'), str) for c in nodes)):
            limitations.append('Personal thread has incomplete evidence')
        source('thread', thread, '#discussion_r' + str(root.get('databaseId', '')))
        if sources and sources[-1]['source_id'] == 'thread:' + str(thread.get('id')) and root.get('url'):
            sources[-1]['url'] = root['url']

    comments = []
    selected = snapshot.get('review_comment_ids', [])
    if not isinstance(selected, list) or any(not _text(cid) for cid in selected):
        raise ValueError('review_comment_ids must be an array of comment IDs')
    selected = set(selected)
    attributed = set()
    comment_ids = set()
    for comment in collections['comments']:
        if not isinstance(comment, dict):
            limitations.append('Malformed issue comment')
            continue
        cid = comment.get('id') or comment.get('databaseId')
        if not cid or str(cid) in comment_ids or not isinstance(comment.get('body'), str):
            limitations.append('Issue comment identity/body is missing or duplicated')
        comment_ids.add(str(cid))
        comments.append(copy.deepcopy(comment))
        # Only explicit personal review markers establish a review; casual
        # participation is context. Assess arbitrary prose semantically later.
        body = activity._without_fenced_code(comment.get('body') or '')
        if (activity.author(comment) == identity['user']
                and (str(cid) in selected or re.search(r'^<!-- cc-review:run-id:[^\s<>]+ -->$', body, re.M))):
            personal = True
            attributed.add(str(cid))
            source('comment', comment, '#issuecomment-' + str(comment.get('databaseId', '')))
    if selected - attributed:
        limitations.append('Manual summary attribution has unknown or foreign comment IDs')
    payload = dict(identity=identity, head_oid=head, sources=sources, context_comments=comments,
                   complete=not limitations, limitations=limitations,
                   follow_up=True if personal else (None if limitations else False))
    payload['fingerprint'] = hashlib.sha256(_json(payload).encode()).hexdigest()
    return payload


def assess(history, head_oid, fingerprint, findings, decisions, concerns,
           coverage_complete, verification_complete):
    """Validate semantic decisions; never turn missing assessments into a clean PR."""
    if not isinstance(history, dict) or any(not isinstance(v, list) for v in (findings, decisions, concerns)):
        raise ValueError('History must be an object and assessment collections must be arrays')
    expected = hashlib.sha256(_json({k: v for k, v in history.items() if k != 'fingerprint'}).encode()).hexdigest()
    limitations = list(history.get('limitations') or [])
    if (head_oid != history.get('head_oid') or fingerprint != history.get('fingerprint')
            or fingerprint != expected):
        limitations.append('History or code changed after assessment')
    if history.get('complete') is not True:
        limitations.append('Conversation history is incomplete')
    result = dict(head_oid=head_oid, fingerprint=fingerprint, findings=[], excluded=[],
                  continuations=[], concerns=[], limitations=limitations,
                  counts=dict(addressed=0, open_material=0, nonblocking=0, new_material=0))
    # Initial reviews retain their existing policy. Unknown history must never
    # take this branch merely because no personal review was visible.
    if history.get('follow_up') is False and not limitations:
        return dict(result, complete=True, conclusion='initial-review', findings=copy.deepcopy(findings))
    if coverage_complete is not True:
        limitations.append('Required reviewer coverage is incomplete')
    if verification_complete is not True:
        limitations.append('Prior-finding verification is incomplete')

    def group(items, key, label):
        groups = {}
        for item in items:
            if not isinstance(item, dict) or not _text(item.get(key)):
                limitations.append('Malformed ' + label)
                continue
            groups.setdefault(item[key], []).append(item)
        return groups

    source_groups = group(history.get('sources', []), 'source_id', 'history source')
    source_ids = set(source_groups)
    concern_groups = group(concerns, 'source_id', 'concern assessment')
    open_sources = set()
    for sid in source_ids:
        matches = concern_groups.pop(sid, [])
        if len(matches) != 1 or len(source_groups[sid]) != 1:
            limitations.append('Missing or duplicate concern assessment: ' + sid)
            continue
        concern = matches[0]
        status = concern.get('status')
        if (status not in ('addressed', 'accepted-explanation', 'open', 'nonblocking', 'unclear')
                or concern.get('code_checked') is not True or not _text(concern.get('evidence'))
                or type(concern.get('material')) is not bool or type(concern.get('question_open')) is not bool
                or (status == 'accepted-explanation' and concern.get('approved') is not True)
                or (status == 'nonblocking' and concern.get('material') is True)):
            limitations.append('Unsupported concern assessment: ' + sid)
            continue
        result['concerns'].append(copy.deepcopy(concern))
        if status == 'unclear' or concern['question_open']:
            limitations.append('Unclear concern or unanswered substantive question: ' + sid)
        if status in ('addressed', 'accepted-explanation'):
            result['counts']['addressed'] += 1
        elif concern['material']:
            open_sources.add(sid)
        else:
            result['counts']['nonblocking'] += 1
    if concern_groups:
        limitations.append('Concern assessments contain unknown sources')

    decision_groups = group(decisions, 'finding_id', 'candidate decision')
    finding_groups = group(findings, 'id', 'finding')
    for fid, candidates in finding_groups.items():
        matches = decision_groups.pop(fid, [])
        finding = candidates[0]
        if len(candidates) != 1 or len(matches) != 1:
            limitations.append('Missing or duplicate candidate decision: ' + fid)
            result['excluded'].append(dict(finding=copy.deepcopy(finding), reason='Unassessed candidate'))
            continue
        decision = matches[0]
        relation = decision.get('relation')
        sid = decision.get('source_id')
        if (relation not in ('new', 'duplicate-of', 'already-answered', 'contradicts-earlier-advice')
                or decision.get('code_checked') is not True or not _text(decision.get('evidence'))
                or type(decision.get('material')) is not bool
                or (relation != 'new' and sid not in source_ids)
                or (relation == 'new' and sid is not None)
                or (finding.get('scope') == 'carried'
                    and (relation == 'new' or sid != 'thread:' + str(finding.get('prior_thread_id'))))
                or (decision.get('material') and not _text(decision.get('impact')))
                or (relation == 'contradicts-earlier-advice' and not _text(decision.get('reversal_reason')))):
            limitations.append('Unsupported continuity decision: ' + fid)
            result['excluded'].append(dict(finding=copy.deepcopy(finding), reason='Unsupported decision'))
            continue
        # Calibration happens before this check. A severity label without
        # actual impact does not make an optional improvement material.
        material = decision['material'] and finding.get('severity') in ('Critical', 'Important')
        if finding.get('resolution') == 'fixed':
            material = False
        if relation != 'new':
            result['continuations'].append(dict(decision, finding=copy.deepcopy(finding),
                                                url=source_groups[sid][0].get('url')))
            if material:
                open_sources.add(sid)
            # Only scope-verified canonical carried concerns remain in the
            # findings array; a manual summary must not invent thread authority.
            if (material and finding.get('scope') == 'carried'
                    and sid == 'thread:' + str(finding.get('prior_thread_id'))):
                result['findings'].append(copy.deepcopy(finding))
        elif material:
            result['findings'].append(copy.deepcopy(finding))
            result['counts']['new_material'] += 1
        if not material:
            result['excluded'].append(dict(finding=copy.deepcopy(finding), reason='Nonblocking follow-up suggestion'))
    if decision_groups:
        limitations.append('Candidate decisions contain unknown findings')
    result['counts']['open_material'] = len(open_sources)
    result['complete'] = not limitations
    result['conclusion'] = ('incomplete' if limitations else 'outstanding material concerns'
                            if open_sources or result['counts']['new_material'] else 'no outstanding material concerns')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'assess'))
    parser.add_argument('--input', required=True)
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.input).read_text())
        result = prepare_history(data) if args.command == 'prepare' else assess(**data)
        print(_json(result))
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(1, 'Error: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
