"""Semantic follow-up scope tests; no network or live PR mutations."""
import copy
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'review/core/scripts'))
try:
    import review_scope as scope
except ModuleNotFoundError:
    scope = None

IDENTITY = dict(host='github.com', repository='acme/widget', user='me', pr=7)
KEY = 'a' * 64


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(scope, 'incremental scope engine is not implemented')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Tester')
        self.git('config', 'user.email', 'tester@example.test')
        self.write('app.py', ''.join('value_%d = %d\n' % (i, i) for i in range(1, 31)))
        self.base = self.commit('base')
        self.git('checkout', '-q', '-b', 'topic')
        self.replace('app.py', 'value_2 = 2', 'value_2 = 20')
        self.old = self.commit('initial contribution')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def write(self, name, body):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def replace(self, name, old, new):
        path = self.repo / name
        path.write_text(path.read_text().replace(old, new))

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def review(self, head=None, run='first', parent=None, root=None, mode='full', user='me', **kw):
        evidence = dict(identity=IDENTITY, run_id=run, mode=mode, head_oid=head or self.old,
                        base_oid=self.base, coverage_key=KEY, complete=True,
                        parent_run_id=parent, root_run_id=root or run)
        evidence.update(kw)
        return dict(author={'login': user}, commit={'oid': evidence['head_oid']},
                    state='COMMENTED', submittedAt='2026-10-28T09:00:00Z',
                    body='<!-- cc-review:run-id:%s -->\n<!-- cc-review-scope:v1 %s -->' %
                         (run, json.dumps(evidence, sort_keys=True)))

    def snapshot(self, **kw):
        result = dict(identity=IDENTITY, head_oid=self.git('rev-parse', 'HEAD'),
                      base_oid=self.git('rev-parse', 'main'), coverage_key=KEY,
                      reviews=[self.review()], reviews_complete=True, full=False,
                      renewed_request=False)
        result.update(kw)
        return result

    def plan(self, **kw):
        return scope.plan_scope(self.repo, self.snapshot(**kw))

    def test_first_legacy_foreign_and_override_use_full(self):
        legacy = self.review()
        legacy['body'] = '<!-- cc-review:run-id:legacy -->'
        for reviews in ([], [legacy], [self.review(user='other')]):
            self.assertEqual('full', self.plan(reviews=reviews)['mode'])
        self.assertEqual('full', self.plan(full=True)['mode'])

    def test_fix_delta_and_completed_no_findings_baseline(self):
        self.replace('app.py', 'value_3 = 3', 'value_3 = 30')
        self.commit('fix')
        review = self.review()
        review['body'] = 'cc-review found no issues at old.\n' + review['body']
        result = self.plan(reviews=[review])
        self.assertEqual('incremental', result['mode'])
        self.assertEqual(self.old, result['baseline']['head_oid'])
        self.assertIn('+value_3 = 30', result['diff'])
        self.assertNotIn('+value_2 = 20', result['diff'])
        self.assertEqual([[3, 3]], result['changes']['app.py'])

    def test_incompatible_coverage_and_broken_chain_use_full(self):
        for review in (self.review(coverage_key='b' * 64),
                       self.review(run='second', mode='incremental', parent='missing', root='first'),
                       self.review(run='cycle', mode='incremental', parent='cycle', root='first')):
            self.assertEqual('full', self.plan(reviews=[review])['mode'])

    def test_completed_chain_is_personal_and_rooted(self):
        self.replace('app.py', 'value_3 = 3', 'value_3 = 30')
        second = self.commit('second')
        review = self.review(head=second, run='second', mode='incremental', parent='first', root='first')
        review['submittedAt'] = '2026-10-28T10:00:00Z'
        self.replace('app.py', 'value_4 = 4', 'value_4 = 40')
        self.commit('third')
        result = self.plan(reviews=[self.review(), review])
        self.assertEqual('incremental', result['mode'])
        self.assertEqual(second, result['baseline']['head_oid'])
        self.assertEqual([[4, 4]], result['changes']['app.py'])

    def rebase(self):
        self.git('checkout', '-q', 'main')
        self.write('upstream.txt', 'upstream only\n')
        self.commit('upstream')
        self.git('checkout', '-q', 'topic')
        self.git('rebase', 'main')

    def test_pure_rebase_has_no_code_review_but_request_is_acknowledged(self):
        self.rebase()
        result = self.plan()
        self.assertEqual('unchanged', result['mode'])
        self.assertFalse(result['review_required'])
        self.assertFalse(result['acknowledgment_required'])
        self.assertTrue(self.plan(renewed_request=True)['acknowledgment_required'])

    def test_mixed_rebase_reviews_only_new_contribution(self):
        self.rebase()
        self.replace('app.py', 'value_4 = 4', 'value_4 = 40')
        self.commit('new contribution')
        result = self.plan()
        self.assertEqual('incremental', result['mode'])
        self.assertEqual({'app.py': [[4, 4]]}, result['changes'])
        self.assertNotIn('upstream.txt', result['diff'])

    def test_conflict_resolution_and_missing_history_fall_back(self):
        self.git('checkout', '-q', 'main')
        self.replace('app.py', 'value_2 = 2', 'value_2 = 200')
        self.commit('conflicting upstream')
        self.git('checkout', '-q', 'topic')
        subprocess.run(['git', '-C', str(self.repo), 'rebase', 'main'], capture_output=True)
        self.replace('app.py', (self.repo / 'app.py').read_text(),
                     ''.join('value_%d = %d\n' % (i, 222 if i == 2 else i) for i in range(1, 31)))
        self.git('add', 'app.py')
        self.git('-c', 'core.editor=true', 'rebase', '--continue')
        self.assertEqual('full', self.plan()['mode'])
        self.assertEqual('full', self.plan(reviews=[self.review(head='f' * 40)])['mode'])

    def test_dirty_checkout_is_not_pinned_and_preserves_index(self):
        self.replace('app.py', 'value_3 = 3', 'value_3 = 30')
        self.git('add', 'app.py')
        before = self.git('diff', '--cached')
        result = self.plan()
        self.assertEqual('full', result['mode'])
        self.assertFalse(result['clean'])
        self.assertFalse(result['complete'])
        self.assertEqual(before, self.git('diff', '--cached'))

    def test_fenced_quoted_duplicate_and_wrong_commit_markers_are_rejected(self):
        for wrap in (lambda b: '```\n' + b + '\n```', lambda b: '> ' + b.replace('\n', '\n> '),
                     lambda b: b + '\n' + b):
            review = self.review()
            review['body'] = wrap(review['body'])
            self.assertEqual('full', self.plan(reviews=[review])['mode'])
        review = self.review()
        review['commit']['oid'] = self.base
        self.assertEqual('full', self.plan(reviews=[review])['mode'])

    def test_spaced_renamed_deleted_and_binary_paths(self):
        self.git('mv', 'app.py', 'renamed app.py')
        self.write('binary.dat', '\x00binary\x00')
        self.commit('rename and binary')
        result = self.plan()
        self.assertEqual('incremental', result['mode'])
        self.assertIn('renamed app.py', result['changes'])
        self.assertIn('binary.dat', result['changes'])
        (self.repo / 'renamed app.py').unlink()
        self.commit('delete')
        self.assertIn('app.py', self.plan()['changes'])
        self.assertEqual([[1, 30]], self.plan()['changes']['app.py'])

    def test_incomplete_reviews_and_invalid_identity_are_not_baselines(self):
        self.assertEqual('full', self.plan(reviews_complete=False)['mode'])
        review = self.review()
        review['body'] += '\n<!-- cc-review-incomplete:v1 -->'
        self.assertEqual('full', self.plan(reviews=[review])['mode'])
        with self.assertRaises(ValueError):
            self.plan(identity=dict(IDENTITY, pr=-1))

    def test_coverage_changes_with_settings_body_or_context(self):
        body = self.repo / 'reviewer.md'
        body.write_text('review policy')
        reviewers = [dict(name='correctness', status='ready', body_file=str(body), reference_files=[])]
        first = scope.coverage_key(reviewers, {'meta': True}, [])
        self.assertNotEqual(first, scope.coverage_key(reviewers, {'meta': False}, []))
        body.write_text('new policy')
        self.assertNotEqual(first, scope.coverage_key(reviewers, {'meta': True}, []))

    def test_coverage_includes_real_descriptor_references_and_command(self):
        ref = self.repo / 'reference.md'
        ref.write_text('policy')
        reviewers = [dict(name='tool', kind='command', status='ready', references=[str(ref)],
                          command={'invoke': 'tool --full'})]
        first = scope.coverage_key(reviewers, {}, [])
        ref.write_text('changed policy')
        self.assertNotEqual(first, scope.coverage_key(reviewers, {}, []))
        second = scope.coverage_key(reviewers, {}, [])
        reviewers[0]['command']['invoke'] = 'tool --other'
        self.assertNotEqual(second, scope.coverage_key(reviewers, {}, []))

    def test_shared_shell_preparation_computes_scope_and_skips_unchanged_dispatch(self):
        self.git('remote', 'add', 'origin', 'https://github.com/acme/widget.git')
        source = Path(__file__).resolve().parents[1]
        command = (source / 'review/core/commands/review.md').read_text()
        section = command.split('## Personal PR Review Scope', 1)[1]
        block = section.split('```bash\n', 1)[1].split('\n```', 1)[0]
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            binary = run / 'bin'
            binary.mkdir()
            fake = binary / 'gh'
            fake.write_text('''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[:2] == ['api', 'user']: print('me')
elif args[:2] == ['repo', 'view']:
    fields = args[args.index('--json')+1]
    if 'nameWithOwner' in fields: print(json.dumps({'nameWithOwner':'acme/widget','url':'https://github.com/acme/widget'}))
    else: print('acme' if fields == 'owner' else 'widget')
elif args[:2] == ['pr', 'view']: print(os.environ['SCOPE_TEST_META'])
elif args[:2] == ['api', 'graphql']:
    key = 'reviewThreads' if 'reviewThreads(first' in ' '.join(args) else 'reviews'
    nodes = [] if key == 'reviewThreads' else json.loads(os.environ.get('SCOPE_TEST_REVIEWS','[]'))
    print(json.dumps({'data':{'repository':{'pullRequest':{key:{'nodes':nodes,'pageInfo':{'hasNextPage':False,'endCursor':None}}}}}}))
else: sys.exit(2)
''')
            fake.chmod(0o755)
            upstream = run / 'github.com/upstream'
            upstream.parent.mkdir()
            subprocess.run(['git','clone','-q','--no-hardlinks',str(self.repo),str(upstream)], check=True)
            for args in (('config','user.name','Upstream'), ('config','user.email','upstream@example.test'),
                         ('checkout','-q','main')):
                subprocess.run(['git','-C',str(upstream),*args], check=True, capture_output=True)
            (upstream / 'upstream-only.txt').write_text('new upstream context\n')
            subprocess.run(['git','-C',str(upstream),'add','.'], check=True)
            subprocess.run(['git','-C',str(upstream),'commit','-qm','upstream'], check=True)
            meta_base = subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD']).decode().strip()
            self.git('config', 'url.' + str(upstream) + '.insteadOf', 'https://github.com/acme/widget.git')
            config = run / 'config.yml'
            config.write_text('reviewers: {}\n')
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
                       CORE_DIR=str(source / 'review/core'), PR_CONTEXT_NUMBER='7',
                       REVIEW_RUN_DIR=str(run / 'artifacts'), WORKER_MODE='false',
                       PROJECT_DIR=str(self.repo), REVIEW_ROOT=str(self.repo),
                       CC_REVIEW_MERGED_CONFIG=str(config), FULL_REVIEW='false', RENEWED_REQUEST='false',
                       REVIEWERS_JSON=json.dumps([dict(name='correctness',kind='prompt',status='ready',
                           body_file=str(source / 'review/core/agents/preamble.md'),references=[])]),
                       SCOPE_TEST_META=json.dumps(dict(state='OPEN',headRefOid=self.old,baseRefOid=meta_base)))
            script = block + '\nprintf "%s" "$REVIEWERS_JSON" > "$REVIEW_RUN_DIR/final-reviewers.json"\n'
            for shell in ('bash', 'zsh'):
                import shutil
                if not shutil.which(shell):
                    continue
                initial = subprocess.run([shell, '-c', 'set -e\n' + script], cwd=self.repo, env=env, capture_output=True)
                self.assertEqual(0, initial.returncode, initial.stderr.decode())
                self.assertEqual('commit', self.git('cat-file','-t',meta_base))
                scope_dir = run / 'artifacts/scope'
                self.assertEqual('full', json.loads((scope_dir / 'scope.json').read_text())['mode'])
                key = json.loads((scope_dir / 'coverage.json').read_text())['coverage_key']
                baseline = self.review(coverage_key=key)
                baseline['comments'] = {'nodes': []}
                env['SCOPE_TEST_REVIEWS'] = json.dumps([baseline])
                completed = subprocess.run([shell, '-c', script], cwd=self.repo, env=env, check=True, capture_output=True)
                prepared = json.loads((scope_dir / 'scope.json').read_text())
                self.assertEqual('unchanged', prepared['mode'], prepared['reason'] + completed.stderr.decode())
                reviewers = json.loads((run / 'artifacts/final-reviewers.json').read_text())
                self.assertEqual('skipped', reviewers[0]['status'])
                env.pop('SCOPE_TEST_REVIEWS', None)

    def test_parser_coverage_tracks_contents_not_installation_path(self):
        first_parser = self.repo / 'first/parse.sh'
        second_parser = self.repo / 'second/parse.sh'
        for path in (first_parser, second_parser):
            path.parent.mkdir()
            path.write_text('parse the findings')
        def descriptor(path):
            return [dict(name='tool', kind='command', status='ready',
                         command={'invoke':'tool', 'output':{'parser':'parse.sh','parser_path':str(path)}})]
        first = scope.coverage_key(descriptor(first_parser), {}, [])
        self.assertEqual(first, scope.coverage_key(descriptor(second_parser), {}, []))
        first_parser.write_text('new parser behavior')
        self.assertNotEqual(first, scope.coverage_key(descriptor(first_parser), {}, []))

    def test_local_non_pr_review_skips_remote_verification_and_completion(self):
        source = Path(__file__).resolve().parents[1]
        command = (source / 'review/core/commands/review.md').read_text()
        sections = command.split('## Prior Finding Verification', 1)[1].split('## Step 3: Dispatch Reviewers', 1)[0]
        blocks = re.findall(r'```bash\n(.*?)\n```', sections, re.S)
        env = dict(os.environ, PR_CONTEXT_NUMBER='', SCOPE_DIR=str(self.repo / 'not-prepared'),
                   SCOPE_TOOL=str(source / 'review/core/scripts/review_scope.py'), RUN_MARKER='local')
        result = subprocess.run(['bash', '-c', 'set -e\n' + '\n'.join(blocks)],
                                cwd=self.repo, env=env, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr.decode())
        self.assertFalse((self.repo / 'not-prepared').exists())


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(scope, 'verification_targets', None)),
                        'explicit verification contract is not implemented')
        from test_pr_actions import thread
        self.thread = thread()
        self.head = 'b' * 40
        self.snapshot = dict(identity=IDENTITY, head_oid=self.head,
                             threads=[self.thread], threads_complete=True)
        self.batch = scope.verification_targets(self.snapshot)

    def outcome(self, status='still-present', **kw):
        result = dict(activity=self.batch['targets'][0]['activity'], status=status,
                      evidence='app.py:2 still permits the unsafe input', code_checked=True,
                      finding=dict(id='FINDING-10', file='app.py', line_start=2,
                                   severity='Important', description='Prior unsafe input concern'))
        result.update(kw)
        return result

    def plan(self, **kw):
        result = dict(mode='incremental', identity=IDENTITY, head_oid=self.head,
                      base_oid='c' * 40, coverage_key=KEY, complete=True, clean=True,
                      changes={'app.py': [[3, 4]]}, baseline=None, required_reviewers=['correctness'])
        result.update(kw)
        return result

    def test_all_owned_old_threads_are_targets_but_foreign_and_resolved_are_not(self):
        older = copy.deepcopy(self.thread)
        older['id'] = 'older'
        older['comments']['nodes'][0]['id'] = 'older-root'
        older['root'] = older['comments']['nodes'][0]
        foreign = copy.deepcopy(self.thread)
        foreign['root']['author'] = {'login': 'someone-else'}
        resolved = copy.deepcopy(self.thread)
        resolved['isResolved'] = True
        result = scope.verification_targets(dict(self.snapshot, threads=[self.thread, older, foreign, resolved]))
        self.assertTrue(result['complete'])
        self.assertEqual({'T1', 'older'}, {t['thread_id'] for t in result['targets']})

    def test_incomplete_thread_history_cannot_be_verified_empty(self):
        self.assertFalse(scope.verification_targets(dict(self.snapshot, threads_complete=False))['complete'])
        self.thread['comments']['pageInfo']['hasNextPage'] = True
        self.assertFalse(scope.verification_targets(self.snapshot)['complete'])

    def test_absent_partial_and_unclear_findings_never_resolve(self):
        for outcomes in ([], [self.outcome()], [self.outcome('unclear')],
                         [self.outcome('confirmed-fixed', evidence='')],
                         [self.outcome('confirmed-fixed', code_checked=False)]):
            result = scope.reconcile_verifications(self.batch, outcomes)
            self.assertEqual([], result['resolutions'])
        result = scope.reconcile_verifications(self.batch, [self.outcome()])
        self.assertTrue(result['complete'])
        self.assertEqual('still-present', result['verified'][0]['status'])

    def test_only_explicit_fix_or_approved_explanation_can_resolve(self):
        fixed = scope.reconcile_verifications(self.batch, [self.outcome('confirmed-fixed')])
        self.assertEqual(['T1'], fixed['resolutions'])
        for approved in (False, True):
            result = scope.reconcile_verifications(self.batch,
                        [self.outcome('accepted-explanation', approved=approved)])
            self.assertEqual(['T1'] if approved else [], result['resolutions'])

    def test_duplicate_or_stale_outcomes_are_incomplete_without_resolutions(self):
        stale = self.outcome('confirmed-fixed')
        stale['activity'] = dict(stale['activity'], head_oid='d' * 40)
        for outcomes in ([stale], [self.outcome('confirmed-fixed')] * 2):
            result = scope.reconcile_verifications(self.batch, outcomes)
            self.assertFalse(result['complete'])
            self.assertEqual([], result['resolutions'])

    def test_scope_filter_requires_changed_lines_or_evidenced_critical_exception(self):
        findings = [dict(id='delta', file='app.py', line_start=3, severity='Important'),
                    dict(id='old', file='app.py', line_start=1, severity='Important'),
                    dict(id='critical-no-proof', file='other.py', line_start=1, severity='Critical'),
                    dict(id='critical', file='other.py', line_start=1, severity='Critical',
                         evidence='other.py:1 demonstrably leaks the token')]
        result = scope.filter_findings(self.plan(), findings, [])
        self.assertEqual(['delta', 'critical'], [f['id'] for f in result['findings']])
        self.assertEqual(['latest_delta', 'unchanged_critical'], [f['scope'] for f in result['findings']])

    def test_still_present_findings_survive_absence_from_new_review(self):
        verified = scope.reconcile_verifications(self.batch, [self.outcome()])['verified']
        result = scope.filter_findings(self.plan(), [], verified)
        self.assertEqual(1, len(result['findings']))
        self.assertEqual('carried', result['findings'][0]['scope'])
        self.assertEqual('Important', result['findings'][0]['severity'])
        again = scope.filter_findings(self.plan(), result['findings'], verified)
        self.assertEqual(1, len(again['findings']))

    def test_carried_findings_require_exact_verified_prior_thread(self):
        finding = dict(id='carried', file='renamed.py', line_start=80, severity='Important', prior_thread_id='T1')
        self.assertEqual([], scope.filter_findings(self.plan(), [finding], [])['findings'])
        verified = scope.reconcile_verifications(self.batch, [self.outcome()])['verified']
        result = scope.filter_findings(self.plan(), [finding], verified)
        self.assertEqual('carried', result['findings'][0]['scope'])

    def test_complete_unresolved_review_can_create_baseline_but_partial_cannot(self):
        verified = scope.reconcile_verifications(self.batch, [self.outcome()])
        reviewers = [dict(name='correctness', required=True, status='ok', actual_scope='full')]
        full = self.plan(mode='full')
        result = scope.completion_marker(full, 'new', reviewers, verified)
        self.assertTrue(result['complete'])
        review = dict(author={'login': 'me'}, state='COMMENTED', commit={'oid': self.head},
                      body='<!-- cc-review:run-id:new -->\n' + result['marker'])
        self.assertEqual(self.head, scope.parse_completion(review, IDENTITY)['head_oid'])
        for plan, results, verification in ((self.plan(clean=False), reviewers, verified),
                (full, [dict(reviewers[0], status='failed')], verified),
                (full, reviewers, dict(verified, complete=False))):
            result = scope.completion_marker(plan, 'new', results, verification)
            self.assertFalse(result['complete'])
            self.assertEqual('', result['marker'])

    def test_completion_rejects_verification_for_another_head_or_identity(self):
        verified = scope.reconcile_verifications(self.batch, [self.outcome()])
        reviewers = [dict(name='correctness', required=True, status='ok', actual_scope='full')]
        for verification in (dict(verified, head_oid='e' * 40),
                             dict(verified, identity=dict(IDENTITY, user='other')),
                             {'complete': True}):
            result = scope.completion_marker(self.plan(mode='full'), 'new', reviewers, verification)
            self.assertFalse(result['complete'])
        delta_only = [dict(reviewers[0], actual_scope='delta')]
        self.assertFalse(scope.completion_marker(self.plan(mode='full'), 'new', delta_only, verified)['complete'])

    def test_malformed_owned_root_is_not_a_verified_empty_queue(self):
        self.thread['root']['body'] = None
        self.assertFalse(scope.verification_targets(self.snapshot)['complete'])

    def test_completion_cannot_omit_or_duplicate_a_required_reviewer(self):
        verified = scope.reconcile_verifications(self.batch, [self.outcome()])
        result = dict(name='correctness', required=True, status='ok', actual_scope='full')
        plan = self.plan(mode='full', required_reviewers=['correctness', 'security'])
        self.assertFalse(scope.completion_marker(plan, 'new', [result], verified)['complete'])
        plan = self.plan(mode='full')
        self.assertFalse(scope.completion_marker(plan, 'new', [result, result], verified)['complete'])

    def test_publication_refresh_rejects_a_changed_conversation(self):
        self.assertTrue(callable(getattr(scope, 'refresh_completion', None)), 'publication refresh missing')
        candidate = dict(scope=self.plan(mode='full'), run_id='new',
                         reviewers=[dict(name='correctness',required=True,status='ok',actual_scope='full')])
        result = scope.refresh_completion(candidate, self.snapshot, [self.outcome()])
        self.assertTrue(result['complete'])
        self.thread['comments']['nodes'][1]['body'] = 'New author reply after preparation'
        self.assertFalse(scope.refresh_completion(candidate, self.snapshot, [self.outcome()])['complete'])


if __name__ == '__main__':
    unittest.main()
