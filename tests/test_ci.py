"""Offline CI policy tests: real coordinator with API transport isolated."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'review/core/scripts/ci.py'


def pr_event(action='opened', fork=False):
    return {'action': action, 'sender': {'login': 'alice'},
            'repository': {'full_name': 'acme/widget'},
            'pull_request': {'number': 7, 'head': {'sha': 'a'*40,
                'repo': {'full_name': 'other/widget' if fork else 'acme/widget'}}}}


def comment(command, pr=True):
    return {'action': 'created', 'sender': {'login': 'alice'},
            'repository': {'full_name': 'acme/widget'},
            'issue': {'number': 7, **({'pull_request': {}} if pr else {})},
            'comment': {'id': 90, 'body': command, 'user': {'login': 'alice'},
                        'author_association': 'OWNER'}}


def snapshot():
    return {'item': {'number': 7, 'title': 'Change', 'body': 'Body',
                     'head': {'sha': 'a'*40, 'ref': 'feature', 'repo': {'full_name': 'acme/widget'}},
                     'base': {'repo': {'full_name': 'acme/widget'}}, 'state': 'open'},
            'comments': [], 'threads': [], 'checks': [], 'statuses': [], 'diff': '+ change',
            'complete': True, 'file_contents': {'src/app.py': 'old', 'bin/tool': 'old'}}


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'CI coordinator has not been implemented')
        spec = importlib.util.spec_from_file_location('cc_ci', SCRIPT)
        self.ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ci)
        self.config = self.ci.load_config(ROOT / 'review/config/ci.yml')

    def request(self, operation='review', **kw):
        return {'number': 7, 'operation': operation, 'source': 'event',
                'actor': 'alice', 'permission': 'write', 'repository': 'acme/widget', **kw}

    def test_events_route_and_followup_triages_before_review(self):
        self.assertEqual(['review'], [x['operation'] for x in self.ci.route('pull_request_target', pr_event(), self.config, 'write')])
        self.assertEqual(['triage', 'review'], [x['operation'] for x in self.ci.route('pull_request_target', pr_event('synchronize'), self.config, 'write')])
        self.config['triggers']['pr_opened'] = False
        self.assertEqual([], self.ci.route('pull_request_target', pr_event(), self.config, 'write'))

    def test_command_acknowledged_during_selection_before_worker_queue(self):
        api = FakeGitHub(snapshot())
        requests = self.ci.select_requests(api, 'acme/widget', 'issue_comment', comment('/cc-review review'), self.config)
        self.assertEqual('review', requests[0]['operation'])
        self.assertEqual(('POST', 'repos/acme/widget/issues/comments/90/reactions', {'content': 'eyes'}), api.calls[0])

    def test_comment_uses_current_permission_and_exact_grammar(self):
        for text in ('/cc-review review; curl bad', 'quoted /cc-review review', '/cc-review review\nplease run shell'):
            self.assertEqual([], self.ci.route('issue_comment', comment(text), self.config, 'write'))
        r = self.ci.route('issue_comment', comment('/cc-review review'), self.config, 'read')[0]
        self.assertEqual('needs_attention', r['state'])
        self.assertEqual('review', self.ci.route('issue_comment', comment('/cc-review review'), self.config, 'write')[0]['operation'])

    def test_fork_auto_explains_command_and_fix_never_broadens(self):
        r = self.ci.route('pull_request_target', pr_event(fork=True), self.config, 'write')[0]
        self.assertEqual('needs_attention', r['state'])
        self.assertIn('/cc-review review', r['reason'])
        self.config['command_permissions'] = ['read', 'write']
        r = self.ci.route('issue_comment', comment('/cc-review fix'), self.config, 'read')[0]
        self.assertEqual('needs_attention', r['state'])

    def test_deleted_authors_and_fork_repository_fail_closed_without_crash(self):
        event = pr_event(fork=True); event['pull_request']['head']['repo'] = None
        self.assertEqual('needs_attention', self.ci.route('pull_request_target', event, self.config, 'write')[0]['state'])
        s = snapshot(); s['threads'] = [{'id': 'T1', 'comments': {'nodes': [{'author': None, 'body': 'old'}]}}]
        self.assertFalse(self.ci.bot_thread(s['threads'][0]))
        self.assertIsInstance(self.ci.fingerprint(s, 'triage', 'github-actions[bot]'), str)

    def test_own_bot_and_disabled_integration_do_nothing(self):
        event = pr_event()
        event['sender']['login'] = self.config['identity']['bot_login']
        self.assertEqual([], self.ci.route('pull_request_target', event, self.config, 'write'))
        self.config['enabled'] = False
        self.assertEqual([], self.ci.route('issue_comment', comment('/cc-review help'), self.config, 'admin'))

    def test_marker_requires_bot_and_current_state_expires_running(self):
        r = self.request(fingerprint='head')
        entry = {'state': 'completed', 'fingerprint': 'head', 'updated_at': 100}
        self.assertFalse(self.ci.eligible(entry, r, 1000, 900))
        entry['fingerprint'] = 'old'
        self.assertTrue(self.ci.eligible(entry, r, 1000, 900))
        entry.update(state='running', updated_at=1000)
        self.assertFalse(self.ci.eligible(entry, r, 1100, 900))
        self.assertTrue(self.ci.eligible(entry, r, 2301, 900))
        body = self.ci.status_body({'review': entry})
        comments = [{'id': 1, 'user': {'login': 'attacker'}, 'body': body}]
        self.assertEqual({}, self.ci.read_status(comments, 'github-actions[bot]')[1])
        comments[0]['user']['login'] = 'github-actions[bot]'
        self.assertEqual(entry, self.ci.read_status(comments, 'github-actions[bot]')[1]['review'])

    def test_assessment_fingerprint_ignores_bot_status_updates(self):
        s = snapshot()
        s['item'].pop('head')
        a = self.ci.fingerprint(s, 'assess', 'github-actions[bot]')
        s['comments'].append({'id': 1, 'body': 'status changed', 'user': {'login': 'github-actions[bot]'}})
        self.assertEqual(a, self.ci.fingerprint(s, 'assess', 'github-actions[bot]'))
        s['comments'].append({'id': 2, 'body': 'new evidence', 'updated_at': 'now', 'user': {'login': 'human'}})
        self.assertNotEqual(a, self.ci.fingerprint(s, 'assess', 'github-actions[bot]'))

    def test_missing_question_or_wrong_mutations_fail_closed(self):
        for value in (None, {}, {'question': 'approve?'}, {'status': 'completed', 'reason': '', 'body': 'ok', 'files': [{'path': 'x', 'content': 'bad'}]}):
            with self.assertRaises(self.ci.CIError):
                self.ci.validate_proposal(self.request(), snapshot(), value, self.config)

    def test_prompt_is_tool_free_and_contains_operation_evidence(self):
        context = {'request': self.request(), 'snapshot': snapshot(), 'config': self.config}
        with tempfile.TemporaryDirectory() as tmp:
            self.ci.write_prompt(context, tmp)
            text = (Path(tmp) / 'prompt.txt').read_text()
            self.assertIn('NO tools', text)
            self.assertIn('"number": 7', text)
            schema = json.loads((Path(tmp) / 'schema.json').read_text())
            self.assertFalse(schema['additionalProperties'])

    def test_project_evidence_is_bounded_and_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / 'project'; project.mkdir()
            (project / 'README.md').write_text('Project purpose')
            (root / 'private').write_text('secret')
            (project / 'AGENTS.md').symlink_to(root / 'private')
            value = self.ci.project_evidence(project)
            self.assertEqual({'README.md': 'Project purpose'}, value)

    def test_review_withholds_failed_or_pending_checks(self):
        p = {'status': 'completed', 'reason': '', 'body': 'A review'}
        self.ci.validate_proposal(self.request(), snapshot(), p, self.config)
        for check in ({'status': 'completed', 'conclusion': 'failure'}, {'status': 'in_progress', 'conclusion': None}):
            s = snapshot(); s['checks'] = [check]
            with self.assertRaises(self.ci.CIError):
                self.ci.validate_proposal(self.request(), s, p, self.config)

    def test_assessment_cannot_complete_without_a_classification_label(self):
        for labels in ([], ['pursue', 'decline'], ['unknown']):
            with self.assertRaises(self.ci.CIError):
                self.ci.validate_proposal(self.request('assess'), snapshot(), {'status': 'completed', 'reason': '', 'body': 'Thanks', 'labels': labels}, self.config)

    def test_triage_cannot_silently_drop_an_unresolved_bot_thread(self):
        s = snapshot(); s['threads'] = [{'id': 'T1', 'isResolved': False, 'comments': {'nodes': [{'author': {'login': 'reviewer[bot]'}, 'body': 'Concern'}]}}]
        with self.assertRaises(self.ci.CIError):
            self.ci.validate_proposal(self.request('triage'), s, {'status': 'completed', 'reason': '', 'replies': []}, self.config)

    def test_human_thread_cannot_be_replied_to_or_resolved(self):
        s = snapshot()
        s['threads'] = [{'id': 'T1', 'isResolved': False, 'comments': {'nodes': [{'author': {'login': 'human'}, 'body': 'please explain'}]}}]
        p = {'status': 'completed', 'reason': '', 'replies': [{'thread_id': 'T1', 'body': 'done', 'resolve': True, 'evidence': 'checked'}]}
        with self.assertRaises(self.ci.CIError):
            self.ci.validate_proposal(self.request('triage'), s, p, self.config)

    def test_fix_rejects_fork_automatic_and_sensitive_paths(self):
        p = {'status': 'completed', 'reason': '', 'files': [{'path': 'src/app.py', 'content': 'fixed'}]}
        self.ci.validate_proposal(self.request('fix', source='comment', comment_id=90), snapshot(), p, self.config)
        s = snapshot(); s['item']['head']['repo']['full_name'] = 'fork/widget'
        with self.assertRaises(self.ci.CIError): self.ci.validate_proposal(self.request('fix', source='comment', comment_id=90), s, p, self.config)
        with self.assertRaises(self.ci.CIError): self.ci.validate_proposal(self.request('fix', source='event'), snapshot(), p, self.config)
        for path in ('../bad', '.github/workflows/run.yml', '.env', 'src/../../x', '/tmp/x', '.cc-review/ci.yml'):
            p['files'][0]['path'] = path
            with self.assertRaises(self.ci.CIError): self.ci.validate_proposal(self.request('fix', source='comment', comment_id=90), snapshot(), p, self.config)

    def test_vertex_model_identifier_supports_version_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ci.yml'
            path.write_text(json.dumps({'provider': 'vertex', 'model': 'claude-sonnet-4-5@20250929'}))
            self.assertEqual('claude-sonnet-4-5@20250929', self.ci.load_config(path)['model'])

    def test_config_rejects_unknown_or_dangerous_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ci.yml'
            for change in ({'schema_version': 99}, {'limits': {'turns': 0}}, {'enabled': 'false'}, {'unknown': True}, {'model': 'x --tools Bash'}, {'model': '--dangerously-skip-permissions'}):
                path.write_text(json.dumps(change))
                with self.assertRaises(self.ci.CIError): self.ci.load_config(path)


class FakeGitHub:
    def __init__(self, evidence):
        self.evidence = copy.deepcopy(evidence)
        self.calls = []
        self.next_id = 100
    def snapshot(self, repo, number, limit, operation=None): return copy.deepcopy(self.evidence)
    def pages(self, path, key=None): return self.call('GET', path)
    def call(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if '/collaborators/' in path: return {'permission': 'write'}
        if path.endswith('/reviews') and method == 'GET': return []
        if path.endswith('/comments') and method == 'POST':
            self.next_id += 1
            c = {'id': self.next_id, 'body': payload['body'], 'user': {'login': 'github-actions[bot]'}}
            self.evidence['comments'].append(c)
            return c
        if '/issues/comments/' in path and method == 'PATCH':
            for c in self.evidence['comments']:
                if str(c['id']) == path.split('/')[-1]: c['body'] = payload['body']
            return {}
        if path.endswith('/reviews') and method == 'POST': return {'id': 9, **payload}
        return {}


class PublisherTests(unittest.TestCase):
    request = PolicyTests.request
    def setUp(self):
        PolicyTests.setUp(self)
        self.api = FakeGitHub(snapshot())
        self.worker = self.ci.Coordinator(self.api, 'acme/widget', self.config, '1', 'https://github.com/acme/widget/actions/runs/1')

    def test_review_posts_comment_and_sticky_status_reused(self):
        context = self.worker.prepare(self.request())
        result = self.worker.finish(context, {'status': 'completed', 'reason': '', 'body': 'Reviewed'})
        self.assertEqual('completed', result['state'])
        reviews = [p for m, url, p in self.api.calls if m == 'POST' and url.endswith('/reviews')]
        self.assertEqual(1, len(reviews)); self.assertEqual('COMMENT', reviews[0]['event'])
        self.assertEqual('a'*40, reviews[0]['commit_id'])
        self.assertEqual(1, len(self.api.evidence['comments']))
        self.assertIsNone(self.worker.prepare(self.request()))

    def test_missing_outcome_and_moved_head_record_attention_without_review(self):
        for proposal, moved in ((None, False), ({'status': 'completed', 'reason': '', 'body': 'Review'}, True)):
            api = FakeGitHub(snapshot())
            worker = self.ci.Coordinator(api, 'acme/widget', self.config, '1', 'https://github.com/acme/widget/actions/runs/1')
            ctx = worker.prepare(self.request())
            if moved: api.evidence['item']['head']['sha'] = 'b'*40
            result = worker.finish(ctx, proposal)
            self.assertEqual('needs_attention', result['state'])
            self.assertFalse(any(m == 'POST' and p.endswith('/reviews') for m, p, _ in api.calls))
            self.assertIn('needs attention', api.evidence['comments'][0]['body'])

    def test_issue_assessment_labels_are_mapped_and_never_closes(self):
        self.api.evidence['item'].pop('head')
        ctx = self.worker.prepare(self.request('assess'))
        result = self.worker.finish(ctx, {'status': 'completed', 'reason': '', 'body': 'Thanks for the example', 'labels': ['pursue']})
        self.assertEqual('completed', result['state'])
        labels = [p for m, url, p in self.api.calls if url.endswith('/labels') and m == 'POST']
        self.assertEqual([{'labels': ['cc-review:pursue']}], labels)
        self.assertFalse(any(p and 'state' in p for _, _, p in self.api.calls))

    def test_fix_preserves_executable_mode_and_updates_ref_without_force(self):
        request = self.request('fix', source='comment', comment_id=90, fingerprint='a'*40)
        old_call = self.api.call
        def call(method, path, payload=None):
            self.api.calls.append((method, path, payload))
            if '/git/commits/' in path: return {'tree': {'sha': 'tree0'}}
            if path.endswith('/git/trees/tree0?recursive=1'):
                return {'tree': [{'path': 'bin/tool', 'mode': '100755', 'type': 'blob'}], 'truncated': False}
            if '/contents/' in path: return {'type': 'file'}
            if method == 'POST' and path.endswith('/git/trees'): return {'sha': 'tree1'}
            if method == 'POST' and path.endswith('/git/commits'): return {'sha': 'commit1'}
            if method == 'GET' and '/pulls/' in path: return self.api.evidence['item']
            return {}
        self.api.call = call
        self.worker.push_fix(request, snapshot(), {'files': [{'path': 'bin/tool', 'content': 'fixed'}]})
        trees = [p for m, u, p in self.api.calls if m == 'POST' and u.endswith('/git/trees')]
        self.assertEqual('100755', trees[0]['tree'][0]['mode'])
        updates = [(u, p) for m, u, p in self.api.calls if m == 'PATCH']
        self.assertEqual([('repos/acme/widget/git/refs/heads/feature', {'sha': 'commit1', 'force': False})], updates)

    def test_failed_refresh_reuses_status_surface(self):
        ctx = self.worker.prepare(self.request())
        def unavailable(*args, **kwargs): raise self.ci.CIError('GitHub unavailable; retry.')
        self.api.snapshot = unavailable
        result = self.worker.finish(ctx, None)
        self.assertEqual('needs_attention', result['state'])
        self.assertEqual(1, len(self.api.evidence['comments']))

    def test_comment_request_requires_real_unchanged_comment(self):
        req = self.request(source='comment', comment_id=90)
        ctx = self.worker.prepare(req)
        self.assertEqual('needs_attention', ctx['terminal']['state'])
        self.assertFalse(any(m == 'POST' and u.endswith('/reviews') for m, u, _ in self.api.calls))

    def test_partial_retry_recovers_published_review_marker(self):
        ctx = self.worker.prepare(self.request())
        marker = self.ci.result_marker(ctx['request'])
        old_call = self.api.call
        def call(method, path, payload=None):
            if method == 'GET' and path.endswith('/reviews'):
                return [{'body': marker, 'user': {'login': 'github-actions[bot]'}, 'commit_id': 'a'*40}]
            return old_call(method, path, payload)
        self.api.call = call
        result = self.worker.finish(ctx, {'status': 'completed', 'reason': '', 'body': 'Reviewed'})
        self.assertEqual('completed', result['state'])
        self.assertFalse(any(m == 'POST' and u.endswith('/reviews') for m, u, _ in self.api.calls))


class SweepTests(unittest.TestCase):
    def setUp(self): PolicyTests.setUp(self)
    def test_sweep_bounded_and_skips_active_and_complete(self):
        api = FakeGitHub(snapshot())
        old_call = api.call
        def call(method, path, payload=None):
            if path.startswith('repos/acme/widget/issues?'):
                return [{'number': 7}, {'number': 8}, {'number': 9}]
            return old_call(method, path, payload)
        api.call = call
        def collect(repo, number, limit):
            s = snapshot(); s['item']['number'] = number
            if number == 7:
                entry = {'state': 'running', 'updated_at': 9999999999, 'fingerprint': 'old'}
                s['comments'] = [{'id': 1, 'user': {'login': 'github-actions[bot]'}, 'body': self.ci.status_body({'review': entry})}]
            return s
        api.snapshot = collect
        self.config['limits']['sweep'] = 1
        requests = self.ci.select_requests(api, 'acme/widget', 'schedule', {}, self.config)
        self.assertEqual([8, 8], [r['number'] for r in requests])
        self.assertEqual(['triage', 'review'], [r['operation'] for r in requests])


class SetupTests(unittest.TestCase):
    def setUp(self): PolicyTests.setUp(self)
    def test_setup_update_disable_preserve_user_files_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.ci.install(root, 'a'*40)
            config = root / '.cc-review/ci.yml'
            value = json.loads(config.read_text()); value['model'] = 'opus'
            config.write_text(json.dumps(value))
            unrelated = root / '.github/workflows/build.yml'; unrelated.write_text('custom')
            caller = root / '.github/workflows/cc-review.yml'
            caller.write_text(caller.read_text() + '# custom caller option\n')
            self.ci.install(root, 'b'*40, update=True)
            self.assertIn('# custom caller option', caller.read_text())
            self.assertEqual('opus', self.ci.load_config(config)['model'])
            self.assertIn('b'*40, (root / '.github/workflows/cc-review.yml').read_text())
            self.ci.disable(root, remove=False)
            self.assertFalse(self.ci.load_config(config)['enabled'])
            self.assertEqual('custom', unrelated.read_text())
            self.ci.disable(root, remove=True)
            self.assertFalse(config.exists()); self.assertTrue(unrelated.exists())
    def test_doctor_reports_missing_credentials_labels_and_plugin_version(self):
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            self.ci.install(tmp, 'a'*40)
            class API:
                def pages(self, path, key=None): return []
                def call(self, method, path, payload=None):
                    if '/contents/review/.claude-plugin/plugin.json' in path:
                        return {'content': base64.b64encode(b'{"version":"1.5.0"}').decode()}
                    if '/runs?' in path: return {'workflow_runs': []}
                    if '/issues?' in path: return []
                    return {}
            result = self.ci.inspect_installation(tmp, 'acme/widget', API())
            self.assertEqual('1.5.0', result['plugin_version'])
            self.assertTrue(any('ANTHROPIC_API_KEY' in x for x in result['issues']))
            self.assertEqual(4, sum('triage label' in x for x in result['issues']))

    def test_setup_rejects_mutable_refs_and_unmanaged_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for ref in ('main', 'v1', 'bad' + 'a'*40):
                with self.assertRaises(self.ci.CIError): self.ci.install(root, ref)
            path = root / '.github/workflows/cc-review.yml'; path.parent.mkdir(parents=True); path.write_text('mine')
            with self.assertRaises(self.ci.CIError): self.ci.install(root, 'a'*40)
            self.assertEqual('mine', path.read_text())


class SnapshotTests(unittest.TestCase):
    def setUp(self): PolicyTests.setUp(self)
    def test_pr_snapshot_only_excludes_its_exact_own_run_and_includes_fix_files(self):
        ci = self.ci
        class API(ci.GitHub):
            def call(self, method, path, payload=None):
                if path.endswith('/issues/7'): return {'pull_request': {}}
                if path.endswith('/pulls/7'): return snapshot()['item']
                if '/comments?' in path: return []
                if '/check-runs?' in path:
                    return {'check_runs': [
                        {'status': 'in_progress', 'conclusion': None, 'details_url': 'https://github.com/acme/widget/actions/runs/123/job/1'},
                        {'status': 'in_progress', 'conclusion': None, 'details_url': 'https://github.com/acme/widget/actions/runs/1234/job/2'}]}
                if path.endswith('/status'): return {'statuses': []}
                if '/files?' in path: return [{'filename': 'src/app.py', 'status': 'modified', 'patch': '+fixed', 'changes': 1}]
                if '/contents/' in path: return {'encoding': 'base64', 'content': 'b2xk'}
                if path == 'graphql': return {'data': {'repository': {'pullRequest': {'reviewThreads': {'pageInfo': {'hasNextPage': False}, 'nodes': []}}}}}
                raise AssertionError(path)
        before = os.environ.get('GITHUB_RUN_ID')
        os.environ['GITHUB_RUN_ID'] = '123'
        try: result = API().snapshot('acme/widget', 7, 100000, operation='fix')
        finally:
            if before is None: os.environ.pop('GITHUB_RUN_ID', None)
            else: os.environ['GITHUB_RUN_ID'] = before
        self.assertEqual(['https://github.com/acme/widget/actions/runs/1234/job/2'], [c['details_url'] for c in result['checks']])
        self.assertEqual({'src/app.py': 'old'}, result['file_contents'])
        self.assertFalse(ci.checks_ok(result))


class CLITests(unittest.TestCase):
    def test_real_prepare_finish_issue_roundtrip_and_missing_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); state = root / 'state.json'
            state.write_text(json.dumps({'comments': [], 'labels': []}))
            gh = root / 'gh'
            gh.write_text(FAKE_GH)
            gh.chmod(0o755)
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                'CI_TEST_STATE': str(state), 'GITHUB_REPOSITORY': 'acme/widget',
                'GITHUB_RUN_ID': '123', 'GITHUB_STEP_SUMMARY': str(root / 'summary'),
                'GITHUB_OUTPUT': str(root / 'outputs')}
            request = json.dumps({'number': 7, 'operation': 'assess', 'source': 'event', 'actor': '', 'permission': 'none'})
            cmd = [sys.executable, '-B', str(SCRIPT), 'prepare', '--config', str(ROOT / 'review/config/ci.yml'), '--request', request, '--work-dir', str(root / 'work')]
            proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn('run_model=true', (root / 'outputs').read_text())
            result = root / 'result.json'
            result.write_text(json.dumps({'status': 'completed', 'reason': '', 'body': 'Thank you. This need fits.', 'labels': ['pursue']}))
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'finish', '--config', str(ROOT / 'review/config/ci.yml'), '--work-dir', str(root / 'work'), '--result', str(result)], env=env, text=True, capture_output=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            value = json.loads(state.read_text())
            self.assertEqual(['cc-review:pursue'], value['labels'])
            self.assertEqual(2, len(value['comments']))
            self.assertIn('completed', value['comments'][0]['body'])
            # Force a new conversation state, then omit the model result.
            value['comments'].append({'id': 900, 'body': 'More evidence', 'user': {'login': 'human'}})
            state.write_text(json.dumps(value))
            self.assertEqual(0, subprocess.run(cmd, env=env, capture_output=True).returncode)
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'finish', '--config', str(ROOT / 'review/config/ci.yml'), '--work-dir', str(root / 'work')], env=env, text=True, capture_output=True)
            self.assertEqual(1, proc.returncode, proc.stderr)
            self.assertIn('needs attention', json.loads(state.read_text())['comments'][0]['body'])
            self.assertIn('needs attention', (root / 'summary').read_text())


FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
path = Path(os.environ['CI_TEST_STATE'])
state = json.loads(path.read_text())
args = sys.argv[1:]
method = args[args.index('--method') + 1]
endpoint = args[args.index('--method') + 2]
payload = json.load(sys.stdin) if '--input' in args else None
if method == 'GET' and endpoint.endswith('/issues/7'):
    out = {'number': 7, 'title': 'Need', 'body': 'A concrete need', 'state': 'open'}
elif method == 'GET' and '/issues/7/comments?' in endpoint:
    out = state['comments']
elif method == 'POST' and endpoint.endswith('/issues/7/comments'):
    out = {'id': len(state['comments']) + 1, 'body': payload['body'], 'user': {'login': 'github-actions[bot]'}}
    state['comments'].append(out)
elif method == 'PATCH' and '/issues/comments/' in endpoint:
    cid = int(endpoint.split('/')[-1])
    for c in state['comments']:
        if c['id'] == cid: c['body'] = payload['body']
    out = {}
elif method == 'POST' and endpoint.endswith('/labels'):
    state['labels'] = payload['labels']; out = {}
else:
    print('Unexpected test API endpoint: ' + endpoint, file=sys.stderr); sys.exit(1)
path.write_text(json.dumps(state))
print(json.dumps(out))
'''


if __name__ == '__main__': unittest.main()
