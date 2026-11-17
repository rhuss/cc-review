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
ASSESSMENT = {
    'kind': 'feature', 'use_case': 'Maintainers want to see which guidance shaped a CI reply.',
    'why': 'They cannot tell a model problem from a missing checkout.', 'concrete_example': True,
    'check': {'result': 'real_need', 'note': 'The reporter hit this while validating v1.6.1.'},
    'severity': 'low', 'severity_reason': 'It slows debugging but blocks nothing.',
    'alternatives': ['Print the commit in the step summary.'], 'fit': 'Yes. `docs/CI.md` documents status.',
    'recommendation': 'pursue', 'recommendation_reason': 'Small and bounded.', 'limits': '',
}


def assess_proposal(body='Thanks for the example.', reason='', **changes):
    value = copy.deepcopy(ASSESSMENT); value.update(changes)
    return {'status': 'completed', 'reason': reason, 'body': body, 'assessment': value}


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

    def test_status_table_renders_outcomes_newest_first(self):
        import calendar
        at = lambda h, m: calendar.timegm((2026, 11, 17, h, m, 0))
        body = self.ci.status_body({
            'assess': {'state': 'completed', 'outcome': 'Assessment posted, labeled `cc-review:pursue`', 'updated_at': at(10, 0), 'run_url': 'https://x/runs/1', 'reason': ''},
            'review': {'state': 'needs_attention', 'reason': 'Checks are still pending.', 'updated_at': at(11, 12), 'run_url': 'https://x/runs/2'}})
        self.assertTrue(body.startswith('### cc-review CI\n'))
        self.assertIn('| Action | Result | Updated | Log |', body)
        self.assertLess(body.index('| review |'), body.index('| assess |'))
        self.assertIn('Needs attention: Checks are still pending.', body)
        self.assertIn('Assessment posted, labeled `cc-review:pursue`', body)
        self.assertIn('2026-11-17 11:12 UTC', body)
        self.assertIn('[run](https://x/runs/2)', body)

    def test_status_help_shows_commands_once(self):
        body = self.ci.status_body({'help': {'state': 'completed', 'outcome': 'Command list shown below', 'updated_at': 1, 'run_url': 'u'}})
        self.assertIn('| help | Command list shown below |', body)
        self.assertEqual(1, body.count('<details><summary>Commands</summary>'))
        self.assertIn('/cc-review fix', body.split('<details>')[1])

    def test_status_table_escapes_cells(self):
        body = self.ci.status_body({'review': {'state': 'needs_attention', 'reason': 'a | b\nc <!-- x -->', 'updated_at': 1, 'run_url': 'u'}})
        row = [line for line in body.splitlines() if line.startswith('| review |')]
        self.assertEqual(1, len(row))
        self.assertIn('a \\| b c &lt;!-- x --&gt;', row[0])
        long = self.ci.status_body({'review': {'state': 'needs_attention', 'reason': 'x' * 400, 'updated_at': 1, 'run_url': 'u'}})
        self.assertNotIn('x' * 301, long.split('<!-- cc-review:ci:v1')[0])

    def test_status_upgrades_v16_comment(self):
        old_entry = {'state': 'completed', 'fingerprint': 'f', 'updated_at': 100, 'run_id': '1', 'run_url': 'u', 'reason': 'Long text.'}
        old_body = ('### cc-review CI\n- **assess**: completed. Long text. [Run](u)\n\n'
                    + self.ci.STATUS_PREFIX + json.dumps({'schema': 1, 'operations': {'assess': old_entry}}, separators=(',', ':')) + ' -->')
        api = FakeGitHub(snapshot())
        worker = self.ci.Coordinator(api, 'acme/widget', self.config, '1', 'https://github.com/acme/widget/actions/runs/1')
        s = snapshot(); s['comments'] = [{'id': 5, 'user': {'login': 'github-actions[bot]'}, 'body': old_body}]
        self.assertEqual(old_entry, self.ci.read_status(s['comments'], 'github-actions[bot]')[1]['assess'])
        worker.status(s, self.request('help', fingerprint='g'), 'completed', outcome='Command list shown below')
        patched = [p['body'] for m, url, p in api.calls if m == 'PATCH']
        self.assertEqual(1, len(patched))
        self.assertIn('| assess | Completed |', patched[0])
        self.assertIn('| help | Command list shown below |', patched[0])
        self.assertNotIn('Long text.', patched[0].split('<!-- cc-review:ci:v1')[0])

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

    def test_prompt_uses_pinned_prose_humanizer_and_falls_back_without_it(self):
        context = {'request': self.request(), 'snapshot': snapshot(), 'config': self.config}
        with tempfile.TemporaryDirectory() as tmp:
            prose = Path(tmp) / 'prose'; skill = prose / 'prose/skills/humanizer/SKILL.md'
            skill.parent.mkdir(parents=True); skill.write_text('# Humanizer\nHUMANIZER-RULES')
            work = Path(tmp) / 'work'
            self.ci.write_prompt(context, work, prose_dir=prose)
            text = (work / 'prompt.txt').read_text()
            self.assertIn('HUMANIZER-RULES', text)
            self.assertLess(text.index('HUMANIZER-RULES'), text.index('untrusted evidence'))
            self.assertIn('Never use em dashes or en dashes', text)
            for config, directory in ((dict(self.config, prose=False), prose), (self.config, Path(tmp) / 'missing'), (self.config, None)):
                self.ci.write_prompt(dict(context, config=config), work, prose_dir=directory)
                text = (work / 'prompt.txt').read_text()
                self.assertNotIn('HUMANIZER-RULES', text)
                self.assertIn('Never use em dashes or en dashes', text)

    def test_prose_setting_defaults_on_and_must_be_boolean(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ci.yml'
            path.write_text('{}'); self.assertTrue(self.ci.load_config(path)['prose'])
            path.write_text('{"prose": false}'); self.assertFalse(self.ci.load_config(path)['prose'])
            path.write_text('{"prose": "yes"}')
            with self.assertRaises(self.ci.CIError): self.ci.load_config(path)

    def test_prompt_carries_issue_assessment_rules(self):
        rules = (ROOT / 'review/core/templates/issue-assessment.md').read_text()
        fit = (ROOT / 'review/core/templates/need-and-fit.md').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            self.ci.write_prompt({'request': self.request('assess'), 'snapshot': snapshot(), 'config': self.config}, tmp)
            text = (Path(tmp) / 'prompt.txt').read_text()
            self.assertIn(rules, text); self.assertIn(fit, text)
            self.ci.write_prompt({'request': self.request('review'), 'snapshot': snapshot(), 'config': self.config}, tmp)
            self.assertNotIn(rules, (Path(tmp) / 'prompt.txt').read_text())

    def test_assess_tools_confined(self):
        with tempfile.TemporaryDirectory() as tmp:
            access = self.ci.model_access('assess', tmp)
            self.assertEqual('Read,Grep,Glob', access['tools'])
            self.assertEqual(str(Path(tmp).resolve()), access['code_dir'])
            for op in ('review', 'triage', 'fix', 'help'):
                self.assertEqual({'tools': '', 'code_dir': ''}, self.ci.model_access(op, tmp))
            self.assertEqual({'tools': '', 'code_dir': ''}, self.ci.model_access('assess', ''))

    def test_prompt_names_readonly_checkout(self):
        context = {'request': self.request('assess'), 'snapshot': snapshot(), 'config': self.config}
        with tempfile.TemporaryDirectory() as tmp:
            self.ci.write_prompt(context, tmp, code_dir='/x/_target')
            text = (Path(tmp) / 'prompt.txt').read_text()
            self.assertIn('/x/_target', text); self.assertIn('read-only', text)
            self.assertNotIn('You have NO tools', text)
            self.ci.write_prompt(context, tmp)
            self.assertIn('code was not available', (Path(tmp) / 'prompt.txt').read_text())

    def test_workflow_confines_model_tools(self):
        text = (ROOT / '.github/workflows/cc-review-reusable.yml').read_text()
        self.assertIn('--tools "${{ steps.prepare.outputs.tools }}"', text)
        self.assertIn('steps.prepare.outputs.code_dir', text)
        self.assertIn('--add-dir', text)
        self.assertIn('--permission-mode dontAsk', text)
        self.assertNotIn('--tools ""', text)
        action = (ROOT / 'ci/action.yml').read_text()
        for name in ('tools', 'code_dir'): self.assertIn(f'steps.prepare.outputs.{name}', action)

    def test_dash_repair_keeps_code_and_numeric_ranges(self):
        text, count = self.ci.repair_dashes(
            'Offline tests — however thorough — cannot speak to it. Pages 3–5 apply.\n'
            'Keep `a — b` and\n```\nx – y\n```\nthe record—actual links—matters.')
        self.assertEqual(
            'Offline tests, however thorough, cannot speak to it. Pages 3-5 apply.\n'
            'Keep `a — b` and\n```\nx – y\n```\nthe record, actual links, matters.', text)
        self.assertEqual(5, count)
        self.assertEqual(('Plain text.', 0), self.ci.repair_dashes('Plain text.'))
        self.assertEqual(('It ends here.', 1), self.ci.repair_dashes('It ends here —.'))

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

    def test_assessment_requires_structured_assessment(self):
        for proposal in ({'status': 'completed', 'reason': '', 'body': 'Thanks', 'labels': ['pursue']},
                         assess_proposal(recommendation='unknown'), assess_proposal(kind='bug')):
            with self.assertRaises(self.ci.CIError):
                self.ci.validate_proposal(self.request('assess'), snapshot(), proposal, self.config)

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

    def test_model_identifier_supports_version_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ci.yml'
            path.write_text(json.dumps({'provider': 'anthropic', 'model': 'claude-sonnet-4-5@20250929'}))
            self.assertEqual('claude-sonnet-4-5@20250929', self.ci.load_config(path)['model'])

    def test_removed_providers_are_rejected_with_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ci.yml'
            for provider in ('oauth', 'vertex', 'bedrock', 'federation'):
                path.write_text(json.dumps({'provider': provider}))
                with self.assertRaises(self.ci.CIError) as caught: self.ci.load_config(path)
                for word in (provider, 'anthropic', 'gateway'): self.assertIn(word, str(caught.exception))
            for provider in ('anthropic', 'gateway'):
                path.write_text(json.dumps({'provider': provider}))
                self.assertEqual(provider, self.ci.load_config(path)['provider'])

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
            self.assertIn('Needs attention:', api.evidence['comments'][0]['body'])

    def posted_comments(self):
        return [p['body'] for m, _, p in self.api.calls if m == 'POST' and 'cc-review:ci-result' in (p or {}).get('body', '')]

    def label_posts(self):
        return [p for m, url, p in self.api.calls if url.endswith('/labels') and m == 'POST']

    def test_assessment_posts_rendered_comment_and_derived_label(self):
        self.api.evidence['item'].pop('head')
        ctx = self.worker.prepare(self.request('assess'))
        result = self.worker.finish(ctx, assess_proposal())
        self.assertEqual('completed', result['state'])
        posted = self.posted_comments()
        self.assertEqual(1, len(posted))
        self.assertTrue(posted[0].startswith('Thanks for the example.'))
        self.assertIn('### Assessment', posted[0])
        self.assertEqual([{'labels': ['cc-review:pursue']}], self.label_posts())
        status = [c['body'] for c in self.api.evidence['comments'] if c['body'].startswith('### cc-review CI')][0]
        self.assertIn('Assessment posted, labeled `cc-review:pursue`', status)
        self.assertFalse(any(p and 'state' in p for _, _, p in self.api.calls))

    def test_assessment_rule_failure_posts_nothing(self):
        self.api.evidence['item'].pop('head')
        ctx = self.worker.prepare(self.request('assess'))
        result = self.worker.finish(ctx, assess_proposal(concrete_example=False))
        self.assertEqual('needs_attention', result['state'])
        self.assertIn('concrete example', result['reason'])
        self.assertEqual([], self.posted_comments())
        self.assertEqual([], self.label_posts())

    def test_assess_labels_must_match_recommendation(self):
        self.api.evidence['item'].pop('head')
        ctx = self.worker.prepare(self.request('assess'))
        proposal = assess_proposal(); proposal['labels'] = ['decline']
        with self.assertRaises(self.ci.CIError):
            self.ci.validate_proposal(self.request('assess'), ctx['snapshot'], proposal, self.config)
        proposal = assess_proposal(); proposal['labels'] = ['cc-review:pursue']
        result = self.worker.finish(ctx, proposal)
        self.assertEqual('completed', result['state'])
        self.assertEqual([{'labels': ['cc-review:pursue']}], self.label_posts())

    def test_schema_enums_have_unique_items(self):
        def walk(node):
            if isinstance(node, dict):
                if 'enum' in node: self.assertEqual(len(node['enum']), len(set(map(json.dumps, node['enum']))), node['enum'])
                for value in node.values(): walk(value)
            elif isinstance(node, list):
                for value in node: walk(value)
        walk(self.ci.proposal_schema(self.config))

    def test_schema_requires_assessment_keys(self):
        schema = self.ci.proposal_schema(self.config)['properties']['assessment']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(sorted(ASSESSMENT), sorted(schema['required']))
        self.assertEqual(sorted(self.config['labels']), schema['properties']['recommendation']['enum'])
        self.assertNotIn('enum', self.ci.PROPOSAL_SCHEMA['properties']['assessment']['properties']['recommendation'])

    def test_completed_status_keeps_model_reason_out(self):
        self.api.evidence['item'].pop('head')
        ctx = self.worker.prepare(self.request('assess'))
        result = self.worker.finish(ctx, assess_proposal(reason='Long internal reasoning'))
        status = [c['body'] for c in self.api.evidence['comments'] if c['body'].startswith('### cc-review CI')][0]
        self.assertNotIn('Long internal reasoning', status.split('<!-- cc-review:ci:v1')[0])
        self.assertIn('Assessment posted, labeled `cc-review:pursue`', status)
        self.assertIn('Long internal reasoning', result['reason'])

    def test_assessment_fields_dash_repaired(self):
        self.api.evidence['item'].pop('head')
        ctx = self.worker.prepare(self.request('assess'))
        result = self.worker.finish(ctx, assess_proposal(body='Clear need — and a good fit.', reason='Assessed.',
                                                         why='Slow — and unclear.'))
        self.assertEqual('completed', result['state'])
        posted = self.posted_comments()
        self.assertEqual(1, len(posted))
        self.assertTrue(posted[0].startswith('Clear need, and a good fit.'))
        self.assertNotIn('—', posted[0])
        self.assertIn('2 dashes replaced', result['reason'])

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
            # A caller from before the rename moves to the new reusable workflow name on update.
            caller.write_text(caller.read_text().replace('cc-review-reusable.yml@', 'cc-review.yml@'))
            self.ci.install(root, 'c'*40, update=True)
            self.assertIn('/.github/workflows/cc-review-reusable.yml@' + 'c'*40, caller.read_text())
            self.assertNotIn('workflows/cc-review.yml@', caller.read_text())
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
            self.assertFalse(any(w in x for x in result['issues'] for w in ('OAUTH', 'Vertex', 'Bedrock', 'FEDERATION')))

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
            result.write_text(json.dumps(assess_proposal(body='Thank you. This need fits.')))
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'finish', '--config', str(ROOT / 'review/config/ci.yml'), '--work-dir', str(root / 'work'), '--result', str(result)], env=env, text=True, capture_output=True)
            self.assertEqual(0, proc.returncode, proc.stderr)
            value = json.loads(state.read_text())
            self.assertEqual(['cc-review:pursue'], value['labels'])
            self.assertEqual(2, len(value['comments']))
            self.assertIn('Assessment posted', value['comments'][0]['body'])
            # Force a new conversation state, then omit the model result.
            value['comments'].append({'id': 900, 'body': 'More evidence', 'user': {'login': 'human'}})
            state.write_text(json.dumps(value))
            self.assertEqual(0, subprocess.run(cmd, env=env, capture_output=True).returncode)
            proc = subprocess.run([sys.executable, '-B', str(SCRIPT), 'finish', '--config', str(ROOT / 'review/config/ci.yml'), '--work-dir', str(root / 'work')], env=env, text=True, capture_output=True)
            self.assertEqual(1, proc.returncode, proc.stderr)
            self.assertIn('Needs attention:', json.loads(state.read_text())['comments'][0]['body'])
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
