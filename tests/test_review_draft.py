"""Review drafts: facts, assembly, preview, fingerprint, conversation diff."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'review/core/scripts/review_draft.py'
FIXTURES = ROOT / 'tests/fixtures/review-draft'
sys.path.insert(0, str(ROOT / 'review/core/scripts'))
import review_draft as rd  # noqa: E402

HEAD = '0123456789abcdef0123456789abcdef01234567'
MARKER = '20261102-120000-review/pr-7'


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def run(*args):
    proc = subprocess.run([sys.executable, '-B', str(SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class Draft:
    """A temporary draft directory built from a slots dict."""

    def __init__(self, test, slots=None, facts='facts-uncurated.json', max_comments=None):
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.dir)]))
        self.slots = copy.deepcopy(slots if slots is not None else fixture('slots-basic.json'))
        self.facts = self.dir / 'facts.json'
        self.facts.write_text((FIXTURES / facts).read_text())
        self.max_comments = max_comments
        self.assemble()

    def assemble(self):
        (self.dir / 'slots.json').write_text(json.dumps(self.slots))
        args = ['assemble', '--slots', self.dir / 'slots.json', '--facts', self.facts,
                '--out', self.dir, '--inputs-key', 'k']
        if self.max_comments is not None:
            args += ['--max-comments', self.max_comments]
        rc, out, err = run(*args)
        assert rc == 0, err
        return out

    @property
    def payload(self):
        return json.loads((self.dir / 'payload.json').read_text())

    def lint(self, expected_head=HEAD, marker=MARKER):
        rc, out, err = run('lint', '--draft', self.dir, '--facts', self.facts,
                           '--expected-head', expected_head, '--run-marker', marker)
        return rc, json.loads((self.dir / 'lint.json').read_text())

    def write_payload(self, payload):
        (self.dir / 'payload.json').write_text(json.dumps(payload))


class FactsTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.dir)]))
        self.facts = self.dir / 'facts.json'

    def read(self):
        return json.loads(self.facts.read_text())

    def test_creates_file_and_sets_curated(self):
        rc, _, err = run('facts-set', '--facts', self.facts, '--curated', 'true')
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read(), {'curated': True, 'executed': []})
        run('facts-set', '--facts', self.facts, '--curated', 'false')
        self.assertFalse(self.read()['curated'])

    def test_appends_executed_entries(self):
        run('facts-set', '--facts', self.facts, '--executed',
            json.dumps({'round': 1, 'command': 'go test ./...', 'outcome': 'failed'}))
        run('facts-set', '--facts', self.facts, '--executed',
            json.dumps({'round': 2, 'command': '', 'outcome': 'no-test-command'}))
        self.assertEqual(self.read()['executed'], [
            {'round': 1, 'command': 'go test ./...', 'outcome': 'failed'},
            {'round': 2, 'command': '', 'outcome': 'no-test-command'}])
        self.assertFalse(self.read()['curated'])

    def test_a_round_recorded_again_replaces_its_entry(self):
        for outcome in ('passed', 'failed'):
            run('facts-set', '--facts', self.facts, '--executed',
                json.dumps({'round': 1, 'command': 'go test ./...', 'outcome': outcome}))
        self.assertEqual(self.read()['executed'], [{'round': 1, 'command': 'go test ./...', 'outcome': 'failed'}])
        self.assertEqual(rd.attribution(rd.load_facts(self.facts)),
                         rd.NOT_CURATED + ' The run executed `go test ./...` in fix round 1: failed.')

    def test_rejects_invalid_entries(self):
        for entry in ({'round': 0, 'command': 'x', 'outcome': 'passed'},
                      {'round': True, 'command': 'x', 'outcome': 'passed'},
                      {'round': 1, 'command': 'x', 'outcome': 'green'},
                      {'round': 1, 'command': '', 'outcome': 'passed'},
                      {'round': 1, 'command': 3, 'outcome': 'passed'}):
            rc, _, err = run('facts-set', '--facts', self.facts, '--executed', json.dumps(entry))
            self.assertEqual(rc, 2, entry)
            self.assertIn('Error:', err)
        self.assertFalse(self.facts.exists())
        rc, _, _ = run('facts-set', '--facts', self.facts, '--executed', 'not json')
        self.assertEqual(rc, 2)
        rc, _, _ = run('facts-set', '--facts', self.facts)
        self.assertEqual(rc, 2)


class FingerprintTest(unittest.TestCase):
    def test_fingerprint_covers_payload_and_thread_actions(self):
        draft = Draft(self)
        meta = json.loads((draft.dir / 'draft.json').read_text())
        rc, out, _ = run('fingerprint', '--draft', draft.dir)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), meta['fingerprint'])
        expected = rd._sha({'payload': draft.payload, 'thread_actions': []})
        self.assertEqual(out.strip(), expected)
        (draft.dir / 'thread-actions.json').write_text(json.dumps(
            [{'thread_id': 'PRRT_1', 'reply_body': 'Fixed.', 'resolve': True, 'activity': {}}]))
        _, changed, _ = run('fingerprint', '--draft', draft.dir)
        self.assertNotEqual(changed.strip(), expected)
        # Formatting does not change the fingerprint, content does
        (draft.dir / 'thread-actions.json').write_text('[]')
        draft.write_payload(draft.payload)
        self.assertEqual(run('fingerprint', '--draft', draft.dir)[1].strip(), expected)
        payload = draft.payload
        payload['event'] = 'REQUEST_CHANGES'
        draft.write_payload(payload)
        self.assertNotEqual(run('fingerprint', '--draft', draft.dir)[1].strip(), expected)

    def test_inputs_key(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(tmp)]))
        a, b = tmp / 'a.json', tmp / 'b.json'
        a.write_text(json.dumps([{'id': 'FINDING-2'}, {'id': 'FINDING-1'}]))
        b.write_text(json.dumps([{'id': 'FINDING-1', 'severity': 'Minor'}, {'id': 'FINDING-2'}]))
        facts = FIXTURES / 'facts-uncurated.json'
        key = lambda f, head=HEAD, fx=facts: run('inputs-key', '--expected-head', head, '--findings', f,
                                                 '--facts', fx)[1].strip()
        self.assertEqual(key(a), key(b), 'only the sorted finding IDs count')
        self.assertEqual(key(a), rd._sha({'expected_head': HEAD, 'finding_ids_to_post': ['FINDING-1', 'FINDING-2'],
                                          'facts': {'curated': False, 'executed': []}}))
        self.assertNotEqual(key(a), key(a, head='f' * 40))
        self.assertNotEqual(key(a), key(a, fx=FIXTURES / 'facts-curated-tested.json'))
        (tmp / 'c.json').write_text(json.dumps([{'id': 'FINDING-1'}]))
        self.assertNotEqual(key(a), key(tmp / 'c.json'))
        (tmp / 'bad.json').write_text(json.dumps([{'severity': 'Minor'}]))
        self.assertEqual(run('inputs-key', '--expected-head', HEAD, '--findings', tmp / 'bad.json',
                             '--facts', facts)[0], 2)


class ConversationDiffTest(unittest.TestCase):
    def setUp(self):
        self.current = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.current)]))
        for name in ('threads.json', 'comments.json', 'reviews.json'):
            (self.current / name).write_text((FIXTURES / 'scope' / name).read_text())

    def edit(self, name, change):
        data = json.loads((self.current / name).read_text())
        change(data)
        (self.current / name).write_text(json.dumps(data))

    def diff(self):
        rc, out, err = run('conversation-diff', '--analysis', FIXTURES / 'scope', '--current', self.current,
                           '--user', 'me')
        self.assertIn(rc, (0, 1), err)
        return rc, json.loads(out)

    def test_unchanged_conversation(self):
        self.assertEqual(self.diff(), (0, []))

    def test_new_items_by_other_people_are_reported(self):
        self.edit('comments.json', lambda d: d.append(
            {'id': 'IC_new', 'body': 'One more thing', 'author': {'login': 'carol', '__typename': 'User'}}))
        self.edit('threads.json', lambda d: d[0]['comments']['nodes'].append(
            {'id': 'PRRC_reply', 'body': 'Still broken', 'author': {'login': 'alice'}}))
        self.edit('threads.json', lambda d: d.append({'id': 'PRRT_new', 'comments': {'nodes': [
            {'id': 'PRRC_root', 'body': 'New concern', 'author': {'login': 'bob'}}]}}))
        self.edit('reviews.json', lambda d: d.append(
            {'databaseId': 999, 'body': 'Looks good', 'author': {'login': 'dave'}, 'state': 'APPROVED'}))
        rc, new = self.diff()
        self.assertEqual(rc, 1)
        self.assertEqual(new, [
            {'kind': 'comment', 'id': 'IC_new', 'author': 'carol'},
            {'kind': 'review', 'id': '999', 'author': 'dave'},
            {'kind': 'review-comment', 'id': 'PRRC_reply', 'author': 'alice'},
            {'kind': 'thread', 'id': 'PRRC_root', 'author': 'bob'}])

    def test_bots_own_items_and_edits_are_ignored(self):
        self.edit('comments.json', lambda d: d.extend([
            {'id': 'IC_bot1', 'body': 'ci', 'author': {'login': 'ci', '__typename': 'Bot'}},
            {'id': 'IC_bot2', 'body': 'ci', 'author': {'login': 'renovate', 'type': 'Bot'}},
            {'id': 'IC_bot3', 'body': 'ci', 'author': {'login': 'dependabot[bot]'}},
            {'id': 'IC_mine', 'body': 'note', 'author': {'login': 'me'}}]))
        self.edit('comments.json', lambda d: d[0].update(body='Edited text', updatedAt='2026-11-01T00:00:00Z'))
        self.edit('reviews.json', lambda d: d.append({'databaseId': 1000, 'author': {'login': 'me'}}))
        self.assertEqual(self.diff(), (0, []))

    def test_identity_is_the_node_id(self):
        # The root of the first thread was deleted: its reply becomes the first
        # comment of the thread, which is not a new item
        self.edit('threads.json', lambda d: d[0]['comments']['nodes'].append(
            {'id': 'PRRC_reply', 'body': 'Reply', 'author': {'login': 'alice'}}))
        analysis = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(analysis)]))
        for name in ('threads.json', 'comments.json', 'reviews.json'):
            (analysis / name).write_text((self.current / name).read_text())
        self.edit('threads.json', lambda d: d[0]['comments'].update(nodes=d[0]['comments']['nodes'][1:]))
        rc, out, err = run('conversation-diff', '--analysis', analysis, '--current', self.current, '--user', 'me')
        self.assertEqual((rc, json.loads(out)), (0, []), err)

    def analysis(self, analyzed_at=None, empty=()):
        """An analysis snapshot from the fixtures; `empty` collections were not read."""
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(directory)]))
        for name in ('threads.json', 'comments.json', 'reviews.json'):
            (directory / name).write_text('[]' if name in empty else (FIXTURES / 'scope' / name).read_text())
        if analyzed_at:
            (directory / 'analyzed-at.json').write_text(json.dumps({'analyzed_at': analyzed_at}))
        return directory

    def diff_against(self, analysis, *extra):
        rc, out, err = run('conversation-diff', '--analysis', analysis, '--current', self.current,
                           '--user', 'me', *extra)
        self.assertIn(rc, (0, 1), err)
        return rc, json.loads(out)

    def test_incomplete_analysis_counts_only_items_created_after_it(self):
        # Nothing was read at analysis time: the existing items are older
        analysis = self.analysis('2026-11-01T12:00:00Z', empty=('threads.json', 'comments.json', 'reviews.json'))
        self.assertEqual(self.diff_against(analysis), (0, []))
        self.edit('comments.json', lambda d: d.extend([
            {'id': 'IC_late', 'createdAt': '2026-11-01T13:00:00Z', 'author': {'login': 'carol'}},
            {'id': 'IC_skew', 'createdAt': '2026-11-01T11:58:00Z', 'author': {'login': 'erin'}},
            {'id': 'IC_old', 'createdAt': '2026-11-01T11:00:00Z', 'author': {'login': 'frank'}}]))
        # A review without a creation time falls back to the identity comparison
        self.edit('reviews.json', lambda d: d.append({'databaseId': 777, 'author': {'login': 'dave'}}))
        self.assertEqual(self.diff_against(analysis), (1, [
            {'kind': 'comment', 'id': 'IC_late', 'author': 'carol'},
            {'kind': 'comment', 'id': 'IC_skew', 'author': 'erin'},
            {'kind': 'review', 'id': '777', 'author': 'dave'}]))

    def test_without_analysis_time_identity_decides(self):
        analysis = self.analysis(empty=('comments.json',))
        self.assertEqual(self.diff_against(analysis), (1, [{'kind': 'comment', 'id': 'IC_kwDOA1', 'author': 'alice'}]))

    def test_ignored_authors_are_treated_like_bots(self):
        self.edit('comments.json', lambda d: d.append(
            {'id': 'IC_robot', 'body': '/retest', 'author': {'login': 'k8s-ci-robot', '__typename': 'User'}}))
        analysis = FIXTURES / 'scope'
        self.assertEqual(self.diff_against(analysis)[0], 1)
        self.assertEqual(self.diff_against(analysis, '--ignore-author', 'k8s-ci-robot'), (0, []))
        self.assertEqual(self.diff_against(analysis, '--ignore-author', 'other-robot')[0], 1)

    def test_missing_current_file_is_an_input_error(self):
        (self.current / 'reviews.json').unlink()
        rc, _, err = run('conversation-diff', '--analysis', FIXTURES / 'scope', '--current', self.current,
                         '--user', 'me')
        self.assertEqual(rc, 2)
        self.assertIn('reviews.json', err)


class HistoryDiffTest(unittest.TestCase):
    """The Follow-up Continuity recheck counts new items by other people only."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.dir)]))
        self.before = {
            'head_oid': HEAD, 'fingerprint': 'a',
            'sources': [
                {'kind': 'thread', 'source_id': 'thread:PRRT_1', 'data': {'id': 'PRRT_1', 'isResolved': False,
                 'comments': {'nodes': [{'id': 'PRRC_1', 'body': 'Fix this', 'createdAt': '2026-10-28T09:00:00Z',
                                         'author': {'login': 'me'}}]}}},
                {'kind': 'review', 'source_id': 'review:301', 'data': {'databaseId': 301, 'body': 'x',
                 'submittedAt': '2026-10-28T09:00:00Z', 'author': {'login': 'me'}}}],
            'context_comments': [{'id': 'IC_1', 'body': 'Thanks', 'createdAt': '2026-10-29T10:00:00Z',
                                  'author': {'login': 'alice'}}]}

    def diff(self, after, *extra):
        (self.dir / 'before.json').write_text(json.dumps(self.before))
        (self.dir / 'after.json').write_text(json.dumps(after))
        rc, out, err = run('history-diff', '--analysis-history', self.dir / 'before.json',
                           '--current-history', self.dir / 'after.json', '--scope', self.dir, '--user', 'me', *extra)
        self.assertIn(rc, (0, 1), err)
        return rc, json.loads(out)

    def test_own_activity_edits_and_pushes_do_not_count(self):
        after = copy.deepcopy(self.before)
        after.update(head_oid='f' * 40, fingerprint='b')
        thread = after['sources'][0]['data']
        thread['isResolved'] = True
        thread['comments']['nodes'].append({'id': 'PRRC_2', 'body': 'Done', 'author': {'login': 'me'}})
        after['sources'].append({'kind': 'review', 'data': {'databaseId': 302, 'author': {'login': 'me'}}})
        after['context_comments'][0].update(body='Thanks a lot', updatedAt='2026-11-02T00:00:00Z')
        after['context_comments'] += [
            {'id': 'IC_bot', 'body': 'coverage', 'author': {'login': 'codecov', '__typename': 'Bot'}},
            {'id': 'IC_robot', 'body': '/retest', 'author': {'login': 'k8s-ci-robot'}}]
        self.assertEqual(self.diff(after, '--ignore-author', 'k8s-ci-robot'), (0, []))

    def test_new_items_by_other_people_count(self):
        after = copy.deepcopy(self.before)
        after['sources'][0]['data']['comments']['nodes'].append(
            {'id': 'PRRC_3', 'body': 'Still broken', 'author': {'login': 'bob'}})
        after['context_comments'].append({'id': 'IC_2', 'body': 'Wait', 'author': {'login': 'carol'}})
        self.assertEqual(self.diff(after), (1, [
            {'kind': 'comment', 'id': 'IC_2', 'author': 'carol'},
            {'kind': 'review-comment', 'id': 'PRRC_3', 'author': 'bob'}]))

    def test_analysis_time_applies(self):
        (self.dir / 'analyzed-at.json').write_text(json.dumps({'analyzed_at': '2026-11-01T12:00:00Z'}))
        after = copy.deepcopy(self.before)
        after['context_comments'] += [
            {'id': 'IC_old', 'body': 'old', 'createdAt': '2026-10-30T00:00:00Z', 'author': {'login': 'carol'}},
            {'id': 'IC_new', 'body': 'new', 'createdAt': '2026-11-01T12:30:00Z', 'author': {'login': 'carol'}}]
        self.assertEqual(self.diff(after), (1, [{'kind': 'comment', 'id': 'IC_new', 'author': 'carol'}]))


class ThreadActionsOnlyFingerprintTest(unittest.TestCase):
    def test_fingerprint_without_payload(self):
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(directory)]))
        self.assertEqual(run('fingerprint', '--draft', directory)[0], 2)
        actions = [{'thread_id': 'PRRT_1', 'reply_body': 'Fixed.', 'resolve': True, 'activity': {}}]
        (directory / 'thread-actions.json').write_text(json.dumps(actions))
        rc, out, err = run('fingerprint', '--draft', directory)
        self.assertEqual((rc, out.strip()), (0, rd._sha({'payload': None, 'thread_actions': actions})), err)


class AssembleTest(unittest.TestCase):
    def headings(self, body):
        return [line for line in body.splitlines() if line.startswith('#')]

    def test_section_order_without_follow_up(self):
        draft = Draft(self)
        self.assertEqual(self.headings(draft.payload['body']), [
            '## cc-review Summary', '### What Went Well', '### Findings', '### Review Details'])
        self.assertEqual(draft.lint(), (0, []))

    def test_section_order_with_follow_up(self):
        draft = Draft(self, fixture('slots-followup.json'))
        body = draft.payload['body']
        self.assertEqual(self.headings(body), [
            '## cc-review Summary', '### Follow-up progress', '### What Went Well', '### Findings',
            '### Review Details'])
        self.assertIn('Two of the three concerns', body)

    def test_review_details_and_marker(self):
        body = Draft(self).payload['body']
        details = body.split('### Review Details\n', 1)[1].splitlines()
        self.assertEqual(details[1], rd.NOT_CURATED)
        self.assertIn('- **Findings posted**: 3', details)
        self.assertIn('- **Findings reviewed and not posted**: 1', details)
        self.assertIn('- **Gate outcome**: FAIL', details)
        self.assertIn('- **Participating reviewers**: correctness, security, test-quality', details)
        self.assertEqual(details[-2:], ['<!-- cc-review:run-id:' + MARKER + ' -->', '<!-- cc-review-incomplete:v1 -->'])

    def test_comment_bodies_and_shapes(self):
        payload = Draft(self).payload
        self.assertEqual(payload['event'], 'COMMENT')
        self.assertEqual(payload['commit_id'], HEAD)
        self.assertEqual(list(payload), ['body', 'event', 'comments', 'commit_id'])
        multi, single = payload['comments']
        self.assertEqual(multi, {
            'path': 'src/parser.go', 'start_line': 40, 'line': 42, 'side': 'RIGHT', 'start_side': 'RIGHT',
            'body': '**Important**: The parser drops the last token when the input ends without a newline.\n\n'
                    '**Why this matters**: Files saved by editors that omit the final newline lose their last '
                    'field, so the import silently truncates data.\n\n'
                    '**Suggested fix**: Flush the pending token after the scan loop ends, before returning the '
                    'result.\n\n_Source: correctness agent (also flagged by: test-quality agent)_'})
        self.assertEqual(set(single), {'path', 'line', 'side', 'body'})
        self.assertEqual(single['line'], 88)
        self.assertTrue(single['body'].startswith('**Critical**: '))

    def test_start_line_equal_to_line_is_single_line(self):
        slots = fixture('slots-basic.json')
        slots['comments'][0]['start_line'] = 42
        comment = Draft(self, slots).payload['comments'][0]
        self.assertNotIn('start_line', comment)
        self.assertEqual(comment['line'], 42)

    def test_removed_comment_drops_row_and_count(self):
        slots = fixture('slots-basic.json')
        slots['comments'][1]['removed'] = True
        payload = Draft(self, slots).payload
        self.assertEqual(len(payload['comments']), 1)
        self.assertNotIn('src/server.go', payload['body'])
        self.assertIn('- **Findings posted**: 2', payload['body'])
        self.assertIn('- **Findings reviewed and not posted**: 2', payload['body'])

    def test_missing_commit_stays_missing(self):
        slots = fixture('slots-basic.json')
        del slots['commit_id']
        draft = Draft(self, slots)
        self.assertNotIn('commit_id', draft.payload)
        rc, findings = draft.lint()
        self.assertEqual(rc, 1)
        self.assertEqual([f['rule'] for f in findings], ['commit'])

    def test_empty_review_is_still_valid(self):
        slots = fixture('slots-basic.json')
        slots.update(comments=[], summary_only=[], went_well=[])
        draft = Draft(self, slots)
        payload = draft.payload
        self.assertEqual(payload['comments'], [])
        self.assertIn('No findings are posted in this review.', payload['body'])
        self.assertIn('- **Findings posted**: 0', payload['body'])
        self.assertNotIn('### What Went Well', payload['body'])
        self.assertEqual(draft.lint(), (0, []))

    def test_truncation_moves_lowest_severity_to_summary(self):
        draft = Draft(self, max_comments=1)
        payload = draft.payload
        self.assertEqual([c['path'] for c in payload['comments']], ['src/server.go'])
        self.assertIn('not inline: Truncated: exceeded maximum inline comment limit (1)', payload['body'])
        self.assertIn('- **Findings posted**: 3', payload['body'])
        moved = json.loads((draft.dir / 'draft.json').read_text())['summary_only']
        self.assertEqual([m['id'] for m in moved], ['FINDING-3', 'FINDING-1'])
        self.assertEqual(draft.lint(), (0, []))

    def test_draft_json_keeps_lint_attempts(self):
        draft = Draft(self)
        meta = json.loads((draft.dir / 'draft.json').read_text())
        self.assertEqual((meta['inputs_key'], meta['lint_attempts']), ('k', 0))
        run('lint', '--draft', draft.dir, '--facts', draft.facts, '--expected-head', HEAD,
            '--run-marker', MARKER, '--count-attempt')
        draft.assemble()
        self.assertEqual(json.loads((draft.dir / 'draft.json').read_text())['lint_attempts'], 1)
        self.assertEqual(json.loads((draft.dir / 'thread-actions.json').read_text()), [])
        self.assertFalse((draft.dir / 'lint.json').exists(), 'assemble drops a stale lint result')

    def test_draft_rebuilt_from_other_inputs_starts_afresh(self):
        draft = Draft(self, max_comments=1)
        run('preview', '--draft', draft.dir)
        for _ in range(2):
            run('lint', '--draft', draft.dir, '--facts', draft.facts, '--expected-head', HEAD,
                '--run-marker', MARKER, '--count-attempt')
        rc, _, err = run('assemble', '--slots', draft.dir / 'slots.json', '--facts', draft.facts,
                         '--out', draft.dir, '--inputs-key', 'other')
        self.assertEqual(rc, 0, err)
        meta = json.loads((draft.dir / 'draft.json').read_text())
        self.assertEqual((meta['inputs_key'], meta['lint_attempts'], meta['max_comments']), ('other', 0, None))
        self.assertFalse((draft.dir / 'preview.md').exists(), 'assemble drops a stale preview')

    def test_summary_only_without_line(self):
        slots = fixture('slots-basic.json')
        slots['summary_only'][0].update(line=None, reason='File no longer exists in this PR.')
        draft = Draft(self, slots)
        body = draft.payload['body']
        self.assertNotIn('None', body)
        self.assertIn('| Minor | docs/usage.md | ', body)
        self.assertIn('- **Minor** `docs/usage.md`: ', body)
        rc, _, _ = run('preview', '--draft', draft.dir)
        self.assertNotIn('None`', (draft.dir / 'preview.md').read_text())

    def test_bad_slots_are_input_errors(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(tmp)]))
        for change in (lambda s: s.update(event='APPROVE'), lambda s: s.pop('run_marker'),
                       lambda s: s['comments'][0].update(line=0),
                       lambda s: s['comments'][0].update(start_line=50)):
            slots = fixture('slots-basic.json')
            change(slots)
            (tmp / 'slots.json').write_text(json.dumps(slots))
            rc, _, err = run('assemble', '--slots', tmp / 'slots.json', '--facts', FIXTURES / 'facts-uncurated.json',
                             '--out', tmp / 'out', '--inputs-key', 'k')
            self.assertEqual(rc, 2, err)


class PreviewTest(unittest.TestCase):
    def preview(self, draft):
        rc, out, err = run('preview', '--draft', draft.dir)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.strip(), str(draft.dir / 'preview.md'))
        return (draft.dir / 'preview.md').read_text()

    def test_all_parts_present(self):
        draft = Draft(self)
        (draft.dir / 'thread-actions.json').write_text(json.dumps(
            [{'thread_id': 'PRRT_kwDOA1', 'reply_body': 'The loop now stops on empty input.', 'resolve': True,
              'activity': {}}]))
        draft.lint()
        text = self.preview(draft)
        self.assertIn('- Review type: plain comment', text)
        self.assertIn(draft.payload['body'], text)
        self.assertIn('### `src/parser.go:40-42`', text)
        self.assertIn('### `src/server.go:88`', text)
        for comment in draft.payload['comments']:
            self.assertIn(comment['body'], text)
        self.assertIn('- **Minor** `docs/usage.md:3`: The usage example still shows the removed `--legacy` flag. '
                      'Reason: Location is outside the PR diff (line 3).', text)
        self.assertIn('- Thread `PRRT_kwDOA1`: reply, resolve yes', text)
        self.assertIn('> The loop now stops on empty input.', text)
        self.assertNotIn('Remaining check findings', text)

    def test_request_for_changes_truncation_and_lint_findings(self):
        slots = fixture('slots-basic.json')
        slots['event'] = 'REQUEST_CHANGES'
        slots['went_well'].append('It works.Really well.')
        draft = Draft(self, slots, max_comments=1)
        draft.lint()
        text = self.preview(draft)
        self.assertIn('- Review type: request for changes', text)
        self.assertIn('Reason: Truncated: exceeded maximum inline comment limit (1)', text)
        self.assertIn('## Remaining check findings', text)
        self.assertIn('[spacing]', text)

    def test_no_inline_comments(self):
        slots = fixture('slots-basic.json')
        slots['comments'] = []
        text = self.preview(Draft(self, slots))
        self.assertIn('## Inline comments\n\nNone.', text)
        self.assertIn('## Summary body', text)

    def test_thread_actions_only(self):
        # No review is posted: the draft holds thread-actions.json alone
        draft = Draft(self)
        (draft.dir / 'payload.json').unlink()
        actions = [{'thread_id': 'PRRT_kwDOA1', 'reply_body': 'The loop now stops on empty input.', 'resolve': True,
                    'activity': {}},
                   {'thread_id': 'PRRT_kwDOA2', 'reply_body': 'Kept as is.\nThe caller checks it.', 'resolve': False,
                    'activity': {}}]
        (draft.dir / 'thread-actions.json').write_text(json.dumps(actions))
        before = run('fingerprint', '--draft', draft.dir)[1]
        text = self.preview(draft)
        self.assertIn('- Review type: none; no review will be posted, only the thread actions below', text)
        self.assertIn('- Proposed thread actions: 2', text)
        self.assertIn('- Thread `PRRT_kwDOA1`: reply, resolve yes', text)
        self.assertIn('> The loop now stops on empty input.', text)
        self.assertIn('- Thread `PRRT_kwDOA2`: reply, resolve no', text)
        self.assertIn('> Kept as is.\n> The caller checks it.', text)
        for part in ('## Summary body', '## Inline comments', 'Pinned commit', 'Remaining check findings'):
            self.assertNotIn(part, text)
        self.assertEqual(run('fingerprint', '--draft', draft.dir)[1], before, 'the preview leaves the fingerprint')
        # Neither a review nor thread actions: nothing to preview
        (draft.dir / 'thread-actions.json').unlink()
        rc, _, err = run('preview', '--draft', draft.dir)
        self.assertEqual(rc, 2)
        self.assertIn('neither payload.json nor thread-actions.json', err)


class ReassembleTest(unittest.TestCase):
    def test_reassembly_keeps_the_inline_limit(self):
        draft = Draft(self, max_comments=1)
        self.assertEqual(len(draft.payload['comments']), 1)
        draft.slots['comments'][1]['what'] = 'Edited by the user.'
        draft.slots['comments'][1]['user_text'] = True
        draft.max_comments = None
        draft.assemble()
        self.assertEqual(len(draft.payload['comments']), 1)
        self.assertEqual(json.loads((draft.dir / 'draft.json').read_text())['max_comments'], 1)
        self.assertIn('Edited by the user.', draft.payload['comments'][0]['body'])


class AttributionTest(unittest.TestCase):
    def statement(self, facts, repro=False):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(tmp)]))
        (tmp / 'facts.json').write_text(json.dumps(facts))
        args = ['attribution', '--facts', tmp / 'facts.json'] + (['--repro'] if repro else [])
        rc, out, err = run(*args)
        self.assertEqual(rc, 0, err)
        return out.strip()

    def test_uncurated_never_claims_curation(self):
        text = self.statement({'curated': False, 'executed': []})
        self.assertEqual(text, rd.NOT_CURATED)
        for word in ('went through', 'selected', 'curated', 'I '):
            self.assertNotIn(word, text)

    def test_curated_says_so(self):
        text = self.statement({'curated': True, 'executed': []})
        self.assertTrue(text.startswith('I went through these findings one by one and selected'))

    def test_executed_entries_of_the_latest_round(self):
        text = self.statement({'curated': False, 'executed': [
            {'round': 1, 'command': 'go test ./...', 'outcome': 'failed'},
            {'round': 2, 'command': 'go test ./...', 'outcome': 'passed'}]})
        self.assertIn('The run executed `go test ./...` in fix round 2: passed.', text)
        self.assertNotIn('fix round 1', text)
        text = self.statement({'curated': False, 'executed': [{'round': 1, 'command': '', 'outcome': 'no-test-command'}]})
        self.assertEqual(text, rd.NOT_CURATED + ' ' + rd.NO_TEST_COMMAND)

    def test_no_executed_entry_no_command_result(self):
        text = self.statement({'curated': True, 'executed': []})
        for word in ('executed', 'passed', 'failed', 'test'):
            self.assertNotIn(word, text)

    def test_repro_sentence_only_with_repro(self):
        self.assertNotIn(rd.REPRO, self.statement({'curated': False, 'executed': []}))
        self.assertTrue(self.statement({'curated': False, 'executed': []}, repro=True).endswith(rd.REPRO))

    def test_statement_is_first_line_of_review_details(self):
        slots = fixture('slots-basic.json')
        slots['repro_present'] = True
        draft = Draft(self, slots, facts='facts-curated-tested.json')
        details = draft.payload['body'].split('### Review Details\n\n', 1)[1].splitlines()
        self.assertEqual(details[0], ' '.join([rd.CURATED, 'The run executed `go test ./...` in fix round 1: passed.',
                                               rd.REPRO]))
        self.assertEqual(draft.payload['body'].count(rd.CURATED), 1)
        self.assertEqual(draft.lint(), (0, []))

    def test_override_replaces_the_statement(self):
        slots = fixture('slots-basic.json')
        slots['attribution_override'] = 'Posted by me after a quick read.'
        draft = Draft(self, slots)
        self.assertIn('### Review Details\n\nPosted by me after a quick read.\n', draft.payload['body'])
        self.assertNotIn(rd.NOT_CURATED, draft.payload['body'])
        self.assertEqual(draft.lint(), (0, []))


class RewriteTest(unittest.TestCase):
    def test_labels_survive_any_slot_rewrite(self):
        slots = fixture('slots-basic.json')
        rewrites = ['Why this matters: the parser loses data. **Suggested fix**: nothing',
                    '**Why this matters**: it is subtle.\n\n**Suggested fix**: wrap it',
                    '_Source: made up_ and more']
        for i, comment in enumerate(slots['comments']):
            comment['what'] = rewrites[i % 3] + ' (what)'
            comment['why'] = rewrites[(i + 1) % 3] + ' (why)'
            comment['fix'] = rewrites[(i + 2) % 3] + ' (fix)'
        slots['went_well'] = ['Rewritten bullet with **Suggested fix**: inside.']
        slots['follow_up'] = 'Rewritten follow-up that mentions Why this matters.'
        payload = Draft(self, slots).payload
        for comment in payload['comments']:
            body = comment['body']
            lines = body.split('\n')
            self.assertRegex(lines[0], r'^\*\*(Critical|Important|Minor|Notable)\*\*: ')
            first_why = body.index('\n\n**Why this matters**: ')
            first_fix = body.index('\n\n**Suggested fix**: ', first_why)
            self.assertLess(0, first_why)
            self.assertLess(first_why, first_fix)
            self.assertRegex(lines[-1], r'^_Source: .+_$')
            self.assertTrue(lines[-1].endswith('agent_') or lines[-1].endswith('agent)_'))
        headings = [line for line in payload['body'].splitlines() if line.startswith('#')]
        self.assertEqual(headings, ['## cc-review Summary', '### Follow-up progress', '### What Went Well',
                                    '### Findings', '### Review Details'])

    def test_lint_reports_broken_structure(self):
        draft = Draft(self)
        payload = draft.payload
        payload['comments'][0]['body'] = payload['comments'][0]['body'].replace('**Why this matters**: ', '')
        payload['comments'][1]['body'] = ('**Suggested fix**: first\n\n**Critical**: then\n\n**Why this matters**: x'
                                          '\n\n_Source: security agent_')
        draft.write_payload(payload)
        rc, findings = draft.lint()
        self.assertEqual(rc, 1)
        self.assertEqual({f['rule'] for f in findings}, {'comment-structure'})
        self.assertTrue(any('Why this matters' in f['message'] for f in findings if 'comment 1' in f['location']))
        self.assertTrue(any('out of order' in f['message'] or 'severity label' in f['message']
                            for f in findings if 'comment 2' in f['location']))


class LintTest(unittest.TestCase):
    def rules(self, draft, **kw):
        rc, findings = draft.lint(**kw)
        self.assertEqual(rc, 1 if findings else 0)
        return [f['rule'] for f in findings]

    def edit_body(self, draft, change):
        payload = draft.payload
        payload['body'] = change(payload['body'])
        draft.write_payload(payload)

    def test_clean_draft_passes(self):
        for name in ('slots-basic.json', 'slots-followup.json'):
            draft = Draft(self, fixture(name))
            self.assertEqual(self.rules(draft), [], name)
            rc, out, _ = run('lint', '--draft', draft.dir, '--facts', draft.facts, '--expected-head', HEAD,
                             '--run-marker', MARKER)
            self.assertEqual((rc, out.strip()), (0, 'LINT ok'))

    def test_marker(self):
        draft = Draft(self)
        self.edit_body(draft, lambda b: b.replace('<!-- cc-review:run-id:' + MARKER + ' -->\n', ''))
        self.assertEqual(self.rules(draft), ['marker'])
        draft = Draft(self)
        self.assertEqual(self.rules(draft, marker='other/pr-7'), ['marker'])

    def test_commit(self):
        draft = Draft(self)
        self.assertEqual(self.rules(draft, expected_head='f' * 40), ['commit'])

    def test_summary_order(self):
        draft = Draft(self, fixture('slots-followup.json'))
        self.edit_body(draft, lambda b: b.replace('### Follow-up progress', '### Temp').replace(
            '### What Went Well', '### Follow-up progress').replace('### Temp', '### What Went Well'))
        self.assertEqual(self.rules(draft), ['summary-order'])
        draft = Draft(self)
        self.edit_body(draft, lambda b: b.replace('### Findings\n', ''))
        self.assertIn('summary-order', self.rules(draft))
        draft = Draft(self)
        self.edit_body(draft, lambda b: b.replace('### Review Details', '### Notes\n\nx\n\n### Review Details'))
        self.assertEqual(self.rules(draft), ['summary-order'])

    def test_attribution(self):
        draft = Draft(self)
        self.edit_body(draft, lambda b: b.replace(rd.NOT_CURATED + '\n', ''))
        self.assertEqual(self.rules(draft), ['attribution'])
        draft = Draft(self)
        self.edit_body(draft, lambda b: b.replace('### What Went Well\n', '### What Went Well\n\n' + rd.NOT_CURATED + '\n'))
        self.assertEqual(self.rules(draft), ['attribution'])
        draft = Draft(self)
        self.edit_body(draft, lambda b: b.replace(rd.NOT_CURATED + '\n\n', '').replace(
            '- **Participating reviewers**', rd.NOT_CURATED + '\n- **Participating reviewers**'))
        self.assertEqual(self.rules(draft), ['attribution'])

    def test_dash_and_spacing_and_claims_in_prose(self):
        slots = fixture('slots-basic.json')
        slots['went_well'][0] = 'The parser is fast \u2014 really fast.'
        self.assertEqual(self.rules(Draft(self, slots)), ['dash'])
        slots = fixture('slots-basic.json')
        slots['comments'][0]['why'] = 'Data is lost.Users notice.'
        self.assertEqual(self.rules(Draft(self, slots)), ['spacing'])
        slots = fixture('slots-basic.json')
        slots['went_well'][0] = 'I ran the tests and they look fine.'
        self.assertEqual(self.rules(Draft(self, slots)), ['claim'])
        slots['went_well'][0] = 'I verified the parser by hand.'
        self.assertEqual(self.rules(Draft(self, slots, facts='facts-curated-tested.json')), ['claim'])
        slots['went_well'][0] = 'I ran the tests after the fix round.'
        self.assertEqual(self.rules(Draft(self, slots, facts='facts-curated-tested.json')), [])
        for claim in ('I’ve tested the parser against the fixtures.', 'I also ran the full suite locally.',
                      'i verified the parser.', 'I have just checked the output.'):
            slots['went_well'][0] = claim
            self.assertEqual(self.rules(Draft(self, slots)), ['claim'], claim)

    def test_claims_in_finding_text_are_not_checked(self):
        slots = fixture('slots-basic.json')
        slots['comments'][0]['what'] = 'I ran this path and it drops the last token.'
        self.assertEqual(self.rules(Draft(self, slots)), [])

    def test_code_urls_and_paths_are_not_prose(self):
        slots = fixture('slots-basic.json')
        slots['went_well'] = ['`a \u2014 b` stays in code; `I ran` too; see https://example.com/a\u2013b?x=1.Y',
                              'The helper in `file.Go` and `e.g.Foo` handles it; lib/x.Go too.']
        slots['comments'][0]['fix'] = 'Use this:\n\n```go\n// I ran it \u2014 done.Next\n```\n\nThen retry.'
        self.assertEqual(self.rules(Draft(self, slots)), [])

    def test_result_phrase_needs_a_recorded_run(self):
        slots = fixture('slots-basic.json')
        slots['went_well'][0] = 'All tests pass at this head.'
        self.assertEqual(self.rules(Draft(self, slots)), ['result'])
        self.assertEqual(self.rules(Draft(self, slots, facts='facts-curated-tested.json')), [])
        slots = fixture('slots-followup.json')
        slots['follow_up'] = 'The fix landed and `go test ./...` passed.'
        self.assertEqual(self.rules(Draft(self, slots)), ['result'])

    def test_result_phrase_needs_a_passing_latest_round(self):
        slots = fixture('slots-basic.json')
        slots['went_well'][0] = 'All tests pass at this head.'
        for executed in ([{'round': 1, 'command': 'go test ./...', 'outcome': 'failed'}],
                         [{'round': 1, 'command': 'go test ./...', 'outcome': 'passed'},
                          {'round': 2, 'command': 'go test ./...', 'outcome': 'failed'}],
                         [{'round': 1, 'command': '', 'outcome': 'no-test-command'}]):
            draft = Draft(self, slots)
            draft.facts.write_text(json.dumps({'curated': False, 'executed': executed}))
            draft.assemble()
            self.assertEqual(self.rules(draft), ['result'], executed)
        # Reporting the recorded failure is not a pass claim
        slots = fixture('slots-followup.json')
        slots['follow_up'] = 'The fix round ran `go test ./...` and it did not pass.'
        draft = Draft(self, slots)
        draft.facts.write_text(json.dumps({'curated': False, 'executed': [
            {'round': 1, 'command': 'go test ./...', 'outcome': 'failed'}]}))
        draft.assemble()
        self.assertEqual(self.rules(draft), [])

    def with_facts(self, slots, executed):
        draft = Draft(self, slots)
        draft.facts.write_text(json.dumps({'curated': False, 'executed': executed}))
        draft.assemble()
        return draft

    def test_named_command_needs_its_own_passing_run(self):
        passed = [{'round': 1, 'command': 'go test ./...', 'outcome': 'passed'}]
        slots = fixture('slots-followup.json')
        # The command that passed in the latest round, in full or by its tool
        for text in ('The fix landed and `go test ./...` passed.', 'The fix landed and go test passes now.'):
            slots['follow_up'] = text
            self.assertEqual(self.rules(self.with_facts(slots, passed)), [], text)
        # Another command than the one that ran is not backed
        for text in ('The fix landed and `npm test` passed.', 'The fix landed and `go test ./pkg/...` passed.'):
            slots['follow_up'] = text
            draft = self.with_facts(slots, passed)
            self.assertEqual(self.rules(draft), ['result'], text)
        # A command that ran but failed in the latest round, while another passed
        mixed = [{'round': 2, 'command': 'go test ./...', 'outcome': 'passed'},
                 {'round': 2, 'command': 'npm test', 'outcome': 'failed'}]
        slots['follow_up'] = 'The fix landed and `npm test` passed.'
        rc, findings = self.with_facts(slots, mixed).lint()
        self.assertEqual([f['rule'] for f in findings], ['result'])
        self.assertIn('npm test passed', findings[0]['message'])
        slots['follow_up'] = 'The fix landed and `go test ./...` passed.'
        self.assertEqual(self.rules(self.with_facts(slots, mixed)), [])
        # A recorded command outside the known tools, passed in an earlier round only
        slots['follow_up'] = 'The fix landed and `./scripts/check.sh` passed.'
        earlier = [{'round': 1, 'command': './scripts/check.sh', 'outcome': 'passed'},
                   {'round': 2, 'command': './scripts/check.sh', 'outcome': 'failed'}]
        self.assertEqual(self.rules(self.with_facts(slots, earlier)), ['result'])
        self.assertEqual(self.rules(self.with_facts(slots, earlier[:1])), [])

    def test_attribution_override_gets_claim_and_result_rules(self):
        slots = fixture('slots-basic.json')
        slots['attribution_override'] = 'I verified every finding by hand.'
        self.assertEqual(self.rules(Draft(self, slots)), ['claim'])
        slots['attribution_override'] = 'Posted after a quick read; all tests pass.'
        self.assertEqual(self.rules(Draft(self, slots)), ['result'])
        slots['attribution_override'] = 'Posted after a quick read; `npm test` passed.'
        self.assertEqual(self.rules(self.with_facts(slots, [
            {'round': 1, 'command': 'go test ./...', 'outcome': 'passed'}])), ['result'])
        slots['attribution_override'] = 'Posted after a quick read; `go test ./...` passed.'
        self.assertEqual(self.rules(self.with_facts(slots, [
            {'round': 1, 'command': 'go test ./...', 'outcome': 'passed'}])), [])
        # An override that is not the first line of Review Details is still checked
        draft = Draft(self, dict(slots, attribution_override='I ran the suite myself.'))
        self.edit_body(draft, lambda b: b.replace('### Review Details\n\nI ran the suite myself.\n',
                                                  '### Review Details\n\nPosted.\n\nI ran the suite myself.\n'))
        self.assertIn('claim', self.rules(draft))

    def test_unsupported_review_type(self):
        draft = Draft(self)
        payload = draft.payload
        payload['event'] = 'APPROVE'
        draft.write_payload(payload)
        self.assertEqual(self.rules(draft), ['event'])
        run('preview', '--draft', draft.dir)
        self.assertIn('- Review type: unsupported review type "APPROVE"', (draft.dir / 'preview.md').read_text())

    def test_count_attempt(self):
        draft = Draft(self)
        for _ in range(2):
            run('lint', '--draft', draft.dir, '--facts', draft.facts, '--expected-head', HEAD,
                '--run-marker', MARKER, '--count-attempt')
        self.assertEqual(json.loads((draft.dir / 'draft.json').read_text())['lint_attempts'], 2)
        rc, out, _ = run('lint', '--draft', draft.dir, '--facts', draft.facts, '--expected-head', 'f' * 40,
                         '--run-marker', MARKER)
        self.assertEqual((rc, out.strip()), (1, 'LINT findings=1'))


CONTINUATIONS = [
    {'thread_id': 'PRRT_kwDOA1', 'reply_body': 'The loop now stops on empty input.', 'resolve': True,
     'activity': {}},
    {'kind': 'continuation', 'thread_id': 'PRRT_kwDOA2', 'source_id': 'thread:PRRT_kwDOA2',
     'reply_body': 'The retry still swallows the timeout error at `src/client.go:51`.', 'resolve': False},
    {'kind': 'pr-comment', 'source_id': 'review:9001',
     'source_url': 'https://github.com/acme/widget/pull/7#pullrequestreview-9001',
     'reply_body': 'Following up on the earlier summary: the config default is still unset.'},
]


class ContinuationActionsTest(unittest.TestCase):
    """Follow-up Continuity responses in thread-actions.json (FR-001)."""

    def draft(self, actions, payload=True, facts='facts-uncurated.json'):
        draft = Draft(self, facts=facts)
        if not payload:
            (draft.dir / 'payload.json').unlink()
        (draft.dir / 'thread-actions.json').write_text(json.dumps(actions))
        return draft

    def lint(self, draft):
        rc, out, err = run('lint', '--draft', draft.dir, '--facts', draft.facts, '--expected-head', HEAD,
                           '--run-marker', MARKER)
        self.assertIn(rc, (0, 1), err)
        return json.loads((draft.dir / 'lint.json').read_text())

    def test_preview_shows_thread_reply_and_pr_comment(self):
        for payload in (True, False):
            draft = self.draft(CONTINUATIONS, payload)
            rc, _, err = run('preview', '--draft', draft.dir)
            self.assertEqual(rc, 0, err)
            text = (draft.dir / 'preview.md').read_text()
            self.assertIn('- Thread `PRRT_kwDOA1`: reply, resolve yes', text)
            self.assertIn('- Thread `PRRT_kwDOA2`: continuation reply, resolve no', text)
            self.assertIn('> The retry still swallows the timeout error at `src/client.go:51`.', text)
            self.assertIn('- PR conversation comment, continues `review:9001` '
                          '(https://github.com/acme/widget/pull/7#pullrequestreview-9001)', text)
            self.assertIn('> Following up on the earlier summary: the config default is still unset.', text)
            if not payload:
                self.assertIn('- Proposed thread actions: 3', text)

    def test_clean_continuations_pass(self):
        for payload in (True, False):
            self.assertEqual(self.lint(self.draft(CONTINUATIONS, payload)), [], payload)

    def test_lint_checks_continuation_text(self):
        actions = copy.deepcopy(CONTINUATIONS)
        actions[1]['reply_body'] = 'Still open \u2014 the retry swallows it.Please check.'
        actions[2]['reply_body'] = 'I verified the default. All tests pass now.'
        for payload in (True, False):
            found = {(f['rule'], f['location']) for f in self.lint(self.draft(actions, payload))}
            self.assertEqual(found, {
                ('dash', 'thread action 2 (thread PRRT_kwDOA2)'),
                ('spacing', 'thread action 2 (thread PRRT_kwDOA2)'),
                ('claim', 'thread action 3 (PR comment)'),
                ('result', 'thread action 3 (PR comment)')}, payload)

    def test_recorded_facts_back_a_continuation(self):
        actions = copy.deepcopy(CONTINUATIONS)
        actions[2]['reply_body'] = 'The run executed `go test ./...` and go test ./... passed.'
        self.assertEqual(self.lint(self.draft(actions, facts='facts-curated-tested.json')), [])
        self.assertEqual([f['rule'] for f in self.lint(self.draft(actions))], ['result'])

    def test_resolution_reply_gets_the_prose_rules_only(self):
        actions = [dict(CONTINUATIONS[0], reply_body='I verified the fix \u2013 it holds.')]
        self.assertEqual([f['rule'] for f in self.lint(self.draft(actions, payload=False))], ['dash'])

    def test_fingerprint_covers_continuations(self):
        draft = self.draft(CONTINUATIONS)
        before = run('fingerprint', '--draft', draft.dir)[1].strip()
        self.assertEqual(before, rd._sha({'payload': draft.payload, 'thread_actions': CONTINUATIONS}))
        for change in (lambda a: a[2].update(reply_body='Changed.'), lambda a: a.pop(1)):
            actions = copy.deepcopy(CONTINUATIONS)
            change(actions)
            (draft.dir / 'thread-actions.json').write_text(json.dumps(actions))
            self.assertNotEqual(run('fingerprint', '--draft', draft.dir)[1].strip(), before)

    def test_invalid_entries_are_usage_errors(self):
        bad = [
            dict(CONTINUATIONS[1], kind='retry'),
            dict(CONTINUATIONS[1], resolve=True),
            dict(CONTINUATIONS[1], thread_id=''),
            dict(CONTINUATIONS[1], reply_body=''),
            dict(CONTINUATIONS[2], thread_id='PRRT_x'),
            {k: v for k, v in CONTINUATIONS[2].items() if k != 'source_id'},
            dict(CONTINUATIONS[0], reply_body=3),
        ]
        for entry in bad:
            draft = self.draft([entry], payload=False)
            for command in (['preview', '--draft', draft.dir],
                            ['lint', '--draft', draft.dir, '--facts', draft.facts, '--expected-head', HEAD,
                             '--run-marker', MARKER]):
                rc, _, err = run(*command)
                self.assertEqual(rc, 2, (entry, command[0]))
                self.assertIn('thread action 1', err)
        # Entries written before the kinds existed stay valid
        legacy = [{'thread_id': 'PRRT_1', 'reply_body': 'Fixed.', 'resolve': True, 'activity': {}}]
        self.assertEqual(self.lint(self.draft(legacy, payload=False)), [])

    def test_lint_needs_a_payload_or_thread_actions(self):
        draft = self.draft([], payload=False)
        (draft.dir / 'thread-actions.json').unlink()
        rc, _, err = run('lint', '--draft', draft.dir, '--facts', draft.facts, '--expected-head', HEAD,
                         '--run-marker', MARKER)
        self.assertEqual(rc, 2)
        self.assertIn('neither payload.json nor thread-actions.json', err)

    def test_duplicate_entries_are_usage_errors(self):
        # A second entry for a thread or a PR comment source would be previewed
        # but skipped at post time, so it is rejected before the preview
        for actions in ([CONTINUATIONS[0], dict(CONTINUATIONS[1], thread_id=CONTINUATIONS[0]['thread_id'])],
                        [CONTINUATIONS[2], dict(CONTINUATIONS[2], reply_body='Another follow-up.')]):
            draft = self.draft(actions, payload=False)
            rc, _, err = run('preview', '--draft', draft.dir)
            self.assertEqual(rc, 2, actions)
            self.assertIn('thread action 2: a second entry for', err)


class Fr009AndTableTest(unittest.TestCase):
    def test_agent_reported_result_labeled_unverified_passes(self):
        slots = fixture('slots-basic.json')
        slots['went_well'][0] = 'A reviewer agent reported that the tests pass; nobody verified this run.'
        rc, findings = Draft(self, slots).lint()
        self.assertEqual((rc, findings), (0, []))
        # Without the label it is still a result claim
        slots['went_well'][0] = 'A reviewer agent reported that the tests pass.'
        self.assertEqual([f['rule'] for f in Draft(self, slots).lint()[1]], ['result'])

    def test_truncated_cell_closes_an_open_code_span(self):
        cell = rd._cell('x' * 90 + ' `some_long_identifier_name` tail', 100)
        self.assertTrue(cell.endswith('...'))
        self.assertEqual(cell.count('`') % 2, 0, cell)
        self.assertLessEqual(len(cell), 100)


if __name__ == '__main__':
    unittest.main()
