"""Conversation continuity and convergence; all hosting boundaries are read-only fakes."""
import copy
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'review/core/scripts'))
try:
    import review_continuity as continuity
except ModuleNotFoundError:
    continuity = None

IDENTITY = dict(host='github.com', repository='acme/widget', user='me', pr=7)
HEAD = 'a' * 40


def review(**kw):
    data = dict(databaseId=12, body='Please avoid losing saved data.', author={'login': 'me'},
                state='COMMENTED', submittedAt='2026-10-28T09:00:00Z',
                url='https://github.com/acme/widget/pull/7#pullrequestreview-12')
    data.update(kw)
    return data


def comment(**kw):
    data = dict(id='IC_1', databaseId=13, body='Why is this needed?', author={'login': 'author'},
                url='https://github.com/acme/widget/pull/7#issuecomment-13',
                createdAt='2026-10-28T10:00:00Z', updatedAt='2026-10-28T10:00:00Z')
    data.update(kw)
    return data


def thread(**kw):
    data = dict(id='PRRT_1', isResolved=True, path='app.py', line=2,
                comments=dict(nodes=[comment(id='PRRC_1', body='Fix data loss', author={'login': 'me'}),
                                     comment(id='PRRC_2')], totalCount=2,
                              pageInfo={'hasNextPage': False, 'hasPreviousPage': False}))
    data.update(kw)
    return data


def snapshot(**kw):
    data = dict(identity=IDENTITY, head_oid=HEAD, reviews=[review()], threads=[], comments=[comment()],
                reviews_complete=True, threads_complete=True, comments_complete=True)
    data.update(kw)
    return data


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(continuity, 'conversation history engine is missing')

    def test_manual_review_preserves_summary_and_unattributed_reply(self):
        history = continuity.prepare_history(snapshot())
        self.assertIs(history['follow_up'], True)
        self.assertTrue(history['complete'])
        self.assertEqual(['review:12'], [s['source_id'] for s in history['sources']])
        self.assertEqual('Why is this needed?', history['context_comments'][0]['body'])
        self.assertEqual('Please avoid losing saved data.', history['sources'][0]['data']['body'])
        self.assertNotIn('baseline', history)

    def test_complete_empty_is_initial_but_failed_empty_is_uncertain(self):
        initial = continuity.prepare_history(snapshot(reviews=[], comments=[]))
        uncertain = continuity.prepare_history(snapshot(reviews=[], comments=[], reviews_complete=False))
        self.assertIs(initial['follow_up'], False)
        self.assertIsNone(uncertain['follow_up'])
        self.assertFalse(uncertain['complete'])

    def test_pending_foreign_and_casual_participation_are_not_personal_reviews(self):
        for previous in (review(state='PENDING'), review(author={'login': 'other'})):
            history = continuity.prepare_history(snapshot(reviews=[previous], comments=[comment(author={'login': 'me'})]))
            self.assertIs(history['follow_up'], False)
            self.assertEqual([], history['sources'])

    def test_pending_inline_draft_does_not_establish_followup(self):
        draft = thread(isResolved=False)
        draft['comments']['nodes'][0]['pullRequestReview'] = {'author':{'login':'me'}, 'body':'', 'state':'PENDING'}
        history = continuity.prepare_history(snapshot(reviews=[review(state='PENDING')], threads=[draft], comments=[]))
        self.assertIs(history['follow_up'], False)
        self.assertEqual([], history['sources'])

    def test_resolved_manual_thread_retains_entire_conversation(self):
        history = continuity.prepare_history(snapshot(reviews=[], threads=[thread()]))
        self.assertIs(history['follow_up'], True)
        source = history['sources'][0]
        self.assertEqual('thread:PRRT_1', source['source_id'])
        self.assertTrue(source['data']['isResolved'])
        self.assertEqual(2, len(source['data']['comments']['nodes']))
        self.assertTrue(source['url'].startswith('https://github.com/acme/widget/pull/7#'))

    def test_personal_marked_summary_comment_establishes_followup(self):
        history = continuity.prepare_history(snapshot(reviews=[], comments=[comment(author={'login': 'me'}, body='Finding\n<!-- cc-review:run-id:abc -->')]))
        self.assertTrue(history['follow_up'])
        self.assertEqual('comment:IC_1', history['sources'][0]['source_id'])

    def test_missing_duplicate_or_truncated_evidence_cannot_be_complete(self):
        for changes in (dict(reviews=[review(), review()]), dict(reviews=[review(databaseId=None)]),
                        dict(threads=[thread(comments={'nodes': [], 'totalCount': 4})]),
                        dict(comments_complete=False), dict(threads_complete=False)):
            with self.subTest(changes=changes):
                history = continuity.prepare_history(snapshot(**changes))
                self.assertFalse(history['complete'])
                self.assertTrue(history['limitations'])

    def test_head_identity_and_reply_changes_invalidate_fingerprint(self):
        first = continuity.prepare_history(snapshot())['fingerprint']
        for changes in (dict(head_oid='b' * 40), dict(identity=dict(IDENTITY, user='other')),
                        dict(comments=[comment(body='I fixed it now')])):
            self.assertNotEqual(first, continuity.prepare_history(snapshot(**changes))['fingerprint'])

    def test_attributed_manual_summary_comment_counts_but_foreign_or_unknown_does_not(self):
        own = comment(id='IC_manual', author={'login': 'me'}, body='The save path loses data on error.')
        history = continuity.prepare_history(snapshot(reviews=[], comments=[own], review_comment_ids=['IC_manual']))
        self.assertTrue(history['follow_up'])
        self.assertEqual('comment:IC_manual', history['sources'][0]['source_id'])
        for comments, selected in (([comment()], ['IC_1']), ([own], ['missing'])):
            history = continuity.prepare_history(snapshot(reviews=[], comments=comments, review_comment_ids=selected))
            self.assertFalse(history['complete'])
            self.assertIsNone(history['follow_up'])

    def test_prepare_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.json'
            path.write_text(json.dumps(snapshot()))
            run = subprocess.run([sys.executable, '-B', str(ROOT / 'review/core/scripts/review_continuity.py'),
                                  'prepare', '--input', str(path)], capture_output=True, text=True)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertTrue(json.loads(run.stdout)['follow_up'])


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(continuity)
        self.history = continuity.prepare_history(snapshot())
        self.concern = dict(source_id='review:12', status='addressed', code_checked=True,
                            evidence='app.py:2 now checks the write result', material=False, question_open=False)
        self.finding = dict(id='FINDING-1', severity='Important', file='app.py', line_start=2,
                            description='Save errors lose user data', rationale='Unchecked failed write',
                            confidence=90, fix='Check result', category='correctness', source_agent='correctness',
                            resolution='pending', round_found=1)
        self.decision = dict(finding_id='FINDING-1', relation='new', code_checked=True,
                             evidence='app.py:2 ignores write failure', material=True,
                             impact='Saved user changes are lost on disk-full errors')

    def assess(self, **kw):
        args = dict(history=self.history, head_oid=HEAD, fingerprint=self.history['fingerprint'],
                    findings=[], decisions=[], concerns=[self.concern], coverage_complete=True,
                    verification_complete=True)
        args.update(kw)
        return continuity.assess(**args)

    def candidate(self, **decision):
        return self.assess(findings=[self.finding], decisions=[dict(self.decision, **decision)])

    def test_verified_fixes_with_only_optional_polish_can_conclude_cleanly(self):
        self.finding['severity'] = 'Minor'
        result = self.candidate(material=False, impact='')
        self.assertEqual('no outstanding material concerns', result['conclusion'])
        self.assertEqual([], result['findings'])
        self.assertEqual(1, len(result['excluded']))

    def test_material_regression_remains_a_new_finding(self):
        result = self.candidate()
        self.assertEqual('outstanding material concerns', result['conclusion'])
        self.assertEqual(['FINDING-1'], [f['id'] for f in result['findings']])
        self.assertEqual(1, result['counts']['new_material'])

    def test_severity_alone_does_not_make_polish_material(self):
        result = self.candidate(material=False, impact='')
        self.assertEqual([], result['findings'])
        self.assertEqual('no outstanding material concerns', result['conclusion'])

    def test_duplicate_promised_fix_continues_in_its_original_conversation(self):
        self.concern.update(status='open', material=True, evidence='The promised change is absent in app.py:2')
        result = self.candidate(relation='duplicate-of', source_id='review:12')
        self.assertEqual([], result['findings'])
        self.assertEqual('review:12', result['continuations'][0]['source_id'])
        self.assertEqual('outstanding material concerns', result['conclusion'])
        self.assertEqual(1, result['counts']['open_material'])

    def test_acknowledged_notable_is_nonblocking_and_not_a_new_comment(self):
        self.concern.update(status='nonblocking', material=False)
        self.finding['severity'] = 'Notable'
        result = self.candidate(relation='duplicate-of', source_id='review:12', material=False)
        self.assertEqual([], result['findings'])
        self.assertEqual('no outstanding material concerns', result['conclusion'])
        self.assertEqual(1, result['counts']['nonblocking'])

    def test_unanswered_author_question_prevents_clean_conclusion(self):
        self.concern.update(question_open=True)
        result = self.assess()
        self.assertEqual('incomplete', result['conclusion'])
        self.assertTrue(result['limitations'])

    def test_reversal_requires_original_source_and_explanation(self):
        result = self.candidate(relation='contradicts-earlier-advice', source_id='review:12')
        self.assertEqual('incomplete', result['conclusion'])
        result = self.candidate(relation='contradicts-earlier-advice', source_id='review:12',
                                reversal_reason='Earlier advice missed the reachable disk-full path')
        self.assertEqual('outstanding material concerns', result['conclusion'])
        self.assertEqual([], result['findings'])
        self.assertIn('disk-full', result['continuations'][0]['reversal_reason'])

    def test_accepted_explanation_requires_existing_explicit_approval(self):
        self.concern.update(status='accepted-explanation')
        self.assertEqual('incomplete', self.assess()['conclusion'])
        self.concern['approved'] = True
        self.assertEqual('no outstanding material concerns', self.assess()['conclusion'])

    def test_missing_duplicate_unknown_and_stale_assessments_fail_closed(self):
        for changes in (dict(concerns=[]), dict(concerns=[self.concern, self.concern]),
                        dict(concerns=[dict(self.concern, source_id='review:unknown')]),
                        dict(head_oid='b' * 40), dict(fingerprint='stale'),
                        dict(concerns=[dict(self.concern, status='promised')]),
                        dict(coverage_complete=False), dict(verification_complete=False)):
            with self.subTest(changes=changes):
                self.assertEqual('incomplete', self.assess(**changes)['conclusion'])
        for decisions in ([], [self.decision, self.decision], [dict(self.decision, finding_id='wrong')],
                          [dict(self.decision, material=True, impact='')],
                          [dict(self.decision, relation='duplicate-of', source_id='thread:foreign')]):
            self.assertEqual('incomplete', self.assess(findings=[self.finding], decisions=decisions)['conclusion'])

    def test_known_carried_material_concern_is_preserved_without_new_inline(self):
        self.history = continuity.prepare_history(snapshot(reviews=[], threads=[thread(isResolved=False)]))
        self.concern.update(source_id='thread:PRRT_1', status='open', material=True)
        self.finding.update(scope='carried', prior_thread_id='PRRT_1')
        result = self.candidate(relation='duplicate-of', source_id='thread:PRRT_1')
        self.assertEqual('carried', result['findings'][0]['scope'])
        self.assertEqual(0, result['counts']['new_material'])
        self.assertEqual(1, result['counts']['open_material'])

    def test_verified_carried_concern_cannot_be_reclassified_as_new(self):
        self.history = continuity.prepare_history(snapshot(reviews=[], threads=[thread(isResolved=False)]))
        self.concern.update(source_id='thread:PRRT_1', status='open', material=True)
        self.finding.update(scope='carried', prior_thread_id='PRRT_1')
        result = self.candidate()
        self.assertFalse(result['complete'])
        self.assertEqual('incomplete', result['conclusion'])
        self.assertEqual(0, result['counts']['new_material'])

    def test_initial_review_keeps_all_original_severities(self):
        self.history = continuity.prepare_history(snapshot(reviews=[], comments=[]))
        self.finding['severity'] = 'Minor'
        result = self.assess(findings=[self.finding], concerns=[])
        self.assertEqual('initial-review', result['conclusion'])
        self.assertEqual('Minor', result['findings'][0]['severity'])

    def test_uncertain_history_never_becomes_an_initial_clean_review(self):
        self.history = continuity.prepare_history(snapshot(reviews=[], comments=[], reviews_complete=False))
        self.assertEqual('incomplete', self.assess(concerns=[])['conclusion'])

    def test_mutated_history_and_duplicate_finding_ids_are_incomplete(self):
        self.history['sources'][0]['data']['body'] = 'Mutated after assessment'
        self.assertEqual('incomplete', self.assess()['conclusion'])
        self.history = continuity.prepare_history(snapshot())
        result = self.assess(findings=[self.finding, self.finding], decisions=[self.decision])
        self.assertEqual('incomplete', result['conclusion'])

    def test_assess_cli_consumes_the_same_artifacts(self):
        data = dict(history=self.history, head_oid=HEAD, fingerprint=self.history['fingerprint'],
                    findings=[], decisions=[], concerns=[self.concern], coverage_complete=True,
                    verification_complete=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.json'
            path.write_text(json.dumps(data))
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'review/core/scripts/review_continuity.py'),
                                     'assess', '--input', str(path)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('no outstanding material concerns', json.loads(result.stdout)['conclusion'])


class WorkflowTests(unittest.TestCase):
    """Execute the actual coordinator code blocks with local JSON artifacts."""
    def block(self, name):
        document = (ROOT / 'review/core/commands/review.md').read_text()
        match = re.search(r'<!-- continuity-' + name + r':start -->\s*```bash\n(.*?)```\s*<!-- continuity-' + name + r':end -->', document, re.S)
        self.assertIsNotNone(match, 'missing executable continuity ' + name + ' contract')
        return match.group(1)

    def run_workflow(self, mode='full', comments_complete=True, manual=False, open_material=False, invalid_threads=False, stale_assessment=False):
        collect = self.block('collect')
        prepare = self.block('prepare')
        assess = self.block('assess')
        with tempfile.TemporaryDirectory(prefix='review continuity ') as tmp:
            folder = Path(tmp)
            (folder / 'scope.json').write_text(json.dumps(dict(identity=IDENTITY, head_oid=HEAD, mode=mode)))
            (folder / 'snapshot.json').write_text(json.dumps(dict(reviews_complete=True)))
            (folder / 'reviews.json').write_text(json.dumps([] if manual else [review()]))
            (folder / 'review-comment-ids.json').write_text(json.dumps(['IC_manual'] if manual else []))
            comments = [comment(id='IC_manual', author={'login': 'me'}, body='The save path loses data.')]
            (folder / 'comments-fixture.json').write_text(json.dumps(comments))
            fake = folder / 'gh'
            fake.write_text("""#!/usr/bin/env python3
import json, pathlib, sys
if sys.argv[1:3] == ['repo','view']:
    print('acme' if 'owner' in sys.argv else 'widget')
    sys.exit()
assert sys.argv[1:3] == ['api','graphql'], sys.argv
query=sys.argv[sys.argv.index('query=')+1] if 'query=' in sys.argv else next(a for a in sys.argv if a.startswith('query='))
kind='reviewThreads' if 'reviewThreads(' in query else 'comments'
if (kind == 'comments' and not COMMENTS_COMPLETE) or (kind == 'reviewThreads' and INVALID_THREADS):
    print(json.dumps({'errors':[{'message':'denied'}], 'data':None}))
else:
    nodes=[] if kind == 'reviewThreads' else json.loads((pathlib.Path(__file__).parent/'comments-fixture.json').read_text())
    print(json.dumps({'data':{'repository':{'pullRequest':{kind:{'nodes':nodes,'pageInfo':{'hasNextPage':False,'endCursor':None}}}}}}))
""".replace('COMMENTS_COMPLETE', repr(comments_complete)).replace('INVALID_THREADS', repr(invalid_threads)))
            fake.chmod(0o755)
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ['PATH'],
                       CORE_DIR=str(ROOT / 'review/core'), SCOPE_DIR=tmp, PR_CONTEXT_NUMBER='7')
            collected = subprocess.run(['bash', '-c', collect + '\n' + prepare], cwd=ROOT, env=env,
                                       capture_output=True, text=True)
            self.assertEqual(0, collected.returncode, collected.stderr)
            history = json.loads((folder / 'history.json').read_text())
            sid = 'comment:IC_manual' if manual else 'review:12'
            concern = dict(source_id=sid, status='open' if open_material else 'addressed',
                           material=open_material, question_open=False, code_checked=True,
                           evidence='app.py:2 inspected at current head')
            for name, value in [('concerns.json', [concern]), ('decisions.json', []),
                                ('candidates.json', []), ('completion.json', {'complete':True}),
                                ('verification.json', {'complete':True}),
                                ('assessment-context.json', {'head_oid':HEAD, 'fingerprint':'stale' if stale_assessment else history['fingerprint']})]:
                (folder / name).write_text(json.dumps(value))
            env['CONTINUITY_CANDIDATES'] = str(folder / 'candidates.json')
            assessed = subprocess.run(['bash','-c',assess], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(0, assessed.returncode, assessed.stderr)
            return history, json.loads((folder / 'continuity.json').read_text())

    def test_full_and_incremental_followups_share_the_executable_contract(self):
        for mode in ('full', 'incremental'):
            with self.subTest(mode=mode):
                history, result = self.run_workflow(mode=mode)
                self.assertTrue(history['follow_up'])
                self.assertEqual('no outstanding material concerns', result['conclusion'])

    def test_manual_summary_only_followup_uses_collected_author_context(self):
        history, result = self.run_workflow(manual=True)
        self.assertEqual('comment:IC_manual', history['sources'][0]['source_id'])
        self.assertEqual('no outstanding material concerns', result['conclusion'])

    def test_partial_collection_withholds_a_clean_result(self):
        history, result = self.run_workflow(comments_complete=False)
        self.assertFalse(history['complete'])
        self.assertEqual('incomplete', result['conclusion'])

    def test_old_semantic_assessments_cannot_be_rebound_to_fresh_history(self):
        history, result = self.run_workflow(stale_assessment=True)
        self.assertTrue(history['complete'])
        self.assertEqual('incomplete', result['conclusion'])

    def test_malformed_thread_collection_cannot_support_a_clean_review(self):
        history, result = self.run_workflow(invalid_threads=True)
        self.assertFalse(history['complete'])
        self.assertEqual('incomplete', result['conclusion'])

    def test_manual_material_concern_blocks_clean_without_a_duplicate_finding(self):
        history, result = self.run_workflow(manual=True, open_material=True)
        self.assertEqual([], result['findings'])
        self.assertEqual(1, result['counts']['open_material'])
        self.assertEqual('outstanding material concerns', result['conclusion'])


class CollectorTests(unittest.TestCase):
    def collect(self, responses, function='fetch_issue_comments acme widget 7', shell='bash', strict=False):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'responses.json').write_text(json.dumps(responses))
            fake = directory / 'gh'
            fake.write_text('''#!/usr/bin/env python3
import json, pathlib, sys
p=pathlib.Path(__file__).parent
assert sys.argv[1:3] == ['api', 'graphql'], sys.argv
assert any('comments(first: 100' in a for a in sys.argv), sys.argv
assert 'cursor=' not in sys.argv, 'empty cursor is not a valid GraphQL cursor'
state=p/'count'
i=int(state.read_text()) if state.exists() else 0
state.write_text(str(i+1))
items=json.loads((p/'responses.json').read_text())
print(json.dumps(items[min(i,len(items)-1)]))
''')
            fake.chmod(0o755)
            return subprocess.run([shell] + (['-u'] if strict else []) + ['-c', 'source "$1"; ' + function, '_',
                                   str(ROOT / 'review/core/scripts/platform.sh')],
                                  env=dict(os.environ, PATH=tmp + os.pathsep + os.environ['PATH']),
                                  cwd=ROOT, capture_output=True, text=True)

    def page(self, nodes, more=False, cursor=None):
        return {'data': {'repository': {'pullRequest': {'comments': {
            'nodes': nodes, 'pageInfo': {'hasNextPage': more, 'endCursor': cursor}}}}}}

    def test_system_bash_nounset_supports_first_page_without_cursor(self):
        result = self.collect([self.page([comment()])], shell='/bin/bash', strict=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('IC_1', json.loads(result.stdout)[0]['id'])

    def test_paginated_comment_collection_preserves_replies(self):
        result = self.collect([self.page([comment()], True, 'next'), self.page([comment(id='IC_2', body='Fixed')])])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(['Why is this needed?', 'Fixed'], [c['body'] for c in json.loads(result.stdout)])

    def test_graphql_error_returns_partial_evidence_and_failure(self):
        result = self.collect([self.page([comment()], True, 'next'), {'errors': [{'message': 'denied'}], 'data': None}])
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(['IC_1'], [c['id'] for c in json.loads(result.stdout)])
        self.assertIn('incomplete', result.stderr.lower())

    def test_null_connection_does_not_become_empty_success(self):
        result = self.collect([{'data': {'repository': {'pullRequest': {'comments': None}}}}])
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], json.loads(result.stdout))

    def test_malformed_review_collection_is_not_empty_success(self):
        result = self.collect([{'errors':[{'message':'denied'}], 'data':None}],
                              function='_github_fetch_reviews acme widget 7')
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], json.loads(result.stdout))

    def test_comment_pagination_cap_is_visible(self):
        result = self.collect([self.page([comment()], True, 'next')])
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(20, len(json.loads(result.stdout)))
        self.assertIn('limit', result.stderr.lower())


if __name__ == '__main__':
    unittest.main()
