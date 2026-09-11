"""Operational recovery and stale-evidence regression tests; no model calls."""
import tempfile
import json
from unittest.mock import patch
from agent.runtime.research.policy import SCHEMA_VERSION, GATE_POLICY_VERSION
from agent.runtime.research.storage import emit, write_json_atomic
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from agent.runtime.research.taskqueue import TaskQueue


class TaskQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.research'
        (self.root / 'control').mkdir(parents=True)
        (self.root / 'control/project.json').write_text(json.dumps({
            'schema_version': SCHEMA_VERSION, 'gate_policy_version': GATE_POLICY_VERSION}))
        (self.root / 'control/state.json').write_text(json.dumps({
            'schema_version': SCHEMA_VERSION, 'policy_status': 'current'}))
        (self.root / 'review').mkdir()
        self.source = self.root / 'review/source.txt'
        self.source.write_text('source v1')
        (self.root / 'review/note.md').write_text('Evidence with location and limits')
        self.q = TaskQueue(self.temp.name)

    def add(self, key='read', depends=()):
        return self.q.apply('add', id=key, question='Does the source support the claim?',
                            acceptance='Locate supporting text and examine limitations',
                            inputs=['review/source.txt'], depends=depends)

    def claim(self, key='read'):
        return self.q.apply('claim', id=key, owner='reader')['token']

    def finish(self, token, key='read'):
        return self.q.apply('finish', id=key, token=token, outputs=['review/note.md'],
                            note='Located passage; limitations recorded')

    def test_restart_and_exclusive_claim(self):
        self.add()
        def attempt(_):
            try:
                return self.claim()
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            tokens = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(token is not None for token in tokens), 1)
        self.q = TaskQueue(self.temp.name)
        self.finish(next(token for token in tokens if token))
        self.assertTrue(self.q.apply('list')['read']['usable'])

    def test_reconcile_revokes_old_claim(self):
        self.add()
        old = self.claim()
        self.q.apply('reconcile', id='read', note='Inspected work; reader stopped, safe to repeat read')
        new = self.claim()
        with self.assertRaises(ValueError):
            self.finish(old)
        self.finish(new)
        self.assertEqual(self.q.apply('list')['read']['attempts'], 2)

    def test_source_change_blocks_completion_and_transitive_reuse(self):
        self.add()
        self.finish(self.claim())
        self.add('synthesize', ['read'])
        self.finish(self.claim('synthesize'), 'synthesize')
        self.source.write_text('source v2 contradicts v1')
        self.assertFalse(self.q.apply('list')['synthesize']['usable'])
        self.q.apply('reconcile', id='read', note='Read revised source')
        self.finish(self.claim())
        self.assertFalse(self.q.apply('list')['synthesize']['usable'])
        self.q.apply('reconcile', id='synthesize', note='Revisit synthesis after revised evidence')
        token = self.claim('synthesize')
        self.source.write_text('source v3')
        with self.assertRaises(ValueError):
            self.finish(token, 'synthesize')

    def test_missing_dependency_empty_output_and_escape_rejected(self):
        with self.assertRaises(ValueError):
            self.add('bad', ['missing'])
        self.add()
        token = self.claim()
        for output in ('review/missing.md', '../outside', 'control/state.json'):
            with self.assertRaises(ValueError):
                self.q.apply('finish', id='read', token=token, outputs=[output], note='checked')
        link = self.root / 'review/link'
        link.symlink_to(self.root / 'control/state.json')
        with self.assertRaises(ValueError):
            self.q.apply('finish', id='read', token=token, outputs=['review/link'], note='checked')
        self.assertEqual(self.q.apply('list')['read']['status'], 'running')

    def test_failed_work_requires_explicit_reconciliation(self):
        self.add()
        self.q.apply('fail', id='read', token=self.claim(), note='Full text unavailable')
        with self.assertRaises(ValueError):
            self.claim()
        with self.assertRaises(ValueError):
            self.q.apply('reconcile', id='read', note=' ')
        self.assertEqual(self.q.apply('list')['read']['status'], 'failed')

    def test_dependency_rerun_invalidates_downstream_even_with_same_files(self):
        self.add()
        self.finish(self.claim())
        self.q.apply('add', id='dependent', question='Synthesize findings',
                     acceptance='Explain agreement', depends=['read'])
        self.finish(self.claim('dependent'), 'dependent')
        self.assertTrue(self.q.apply('list')['dependent']['usable'])
        self.q.apply('reconcile', id='read', note='Reassess interpretation with same source')
        self.finish(self.claim())
        self.assertFalse(self.q.apply('list')['dependent']['usable'])

    def test_dependency_rerun_blocks_inflight_completion(self):
        self.add()
        self.finish(self.claim())
        self.q.apply('add', id='dependent', question='Synthesize findings',
                     acceptance='Explain agreement', depends=['read'])
        token = self.claim('dependent')
        self.q.apply('reconcile', id='read', note='Reassess interpretation')
        self.finish(self.claim())
        with self.assertRaises(ValueError):
            self.finish(token, 'dependent')


    def test_symlink_substitution_is_not_silently_accepted(self):
        self.add()
        self.finish(self.claim())
        original = self.root / 'review/original.txt'
        self.source.rename(original)
        self.source.symlink_to(original)
        self.assertFalse(self.q.apply('list')['read']['usable'])
        with self.assertRaisesRegex(ValueError, 'symbolic links'):
            self.q.apply('reconcile', id='read', note='Try rereading alias')

    def test_queue_mutation_obeys_project_policy_and_event_integrity(self):
        self.add()
        before = self.q.path.read_bytes()
        state = self.root / 'control/state.json'
        state.write_text(json.dumps({'schema_version': SCHEMA_VERSION, 'policy_status': 'migration-required'}))
        self.assertIn('read', self.q.apply('list'))  # Diagnostics remain available.
        with self.assertRaisesRegex(SystemExit, 'migration-required'):
            self.claim()
        self.assertEqual(before, self.q.path.read_bytes())
        state.write_text(json.dumps({'schema_version': SCHEMA_VERSION, 'policy_status': 'current'}))
        emit(self.q.root, 'test', 'test', {})
        events = self.root / 'control/events.jsonl'
        record = json.loads(events.read_text())
        record['actor'] = 'changed'
        events.write_text(json.dumps(record) + '\n')
        with self.assertRaisesRegex(SystemExit, 'integrity failure'):
            self.claim()
        self.assertEqual(before, self.q.path.read_bytes())

    def test_cancel_missing_input_revokes_claim_and_blocks_dependents(self):
        self.add()
        token = self.claim()
        self.q.apply('add', id='dependent', question='Synthesize', acceptance='Compare', depends=['read'])
        self.source.unlink()
        self.q.apply('cancel', id='read', note='Source removed; verified no external worker remains')
        self.assertEqual(self.q.apply('list')['read']['status'], 'cancelled')
        self.assertFalse(self.q.apply('list')['dependent']['ready'])
        with self.assertRaises(ValueError):
            self.finish(token)
        self.source.write_text('replacement source')
        self.q.apply('reconcile', id='read', note='Source restored; reread required')
        self.finish(self.claim())
        self.assertTrue(self.q.apply('list')['dependent']['ready'])

    def test_malformed_queue_fails_without_overwriting_history(self):
        self.add()
        original = json.loads(self.q.path.read_text())
        variants = [[], {'version': 1, 'tasks': []}]
        for change in ({'dependencies': ['read']}, {'dependencies': ['missing']},
                       {'status': 'complete', 'attempts': 1, 'dependency_attempts': {}},
                       {'inputs': []}, {'attempts': True}):
            data = json.loads(json.dumps(original))
            data['tasks']['read'].update(change)
            variants.append(data)
        for data in variants:
            with self.subTest(data=data):
                self.q.path.write_text(json.dumps(data))
                before = self.q.path.read_bytes()
                with self.assertRaises(ValueError):
                    self.q.apply('list')
                with self.assertRaises(ValueError):
                    self.claim()
                self.assertEqual(before, self.q.path.read_bytes())

    def test_long_shared_dependency_graph_hashes_each_file_once(self):
        self.add()
        self.finish(self.claim())
        data = json.loads(self.q.path.read_text())
        template = data['tasks']['read']
        for index in range(1100):
            key = f'node-{index}'
            dependencies = ['read'] + ([f'node-{index-1}'] if index else [])
            task = json.loads(json.dumps(template))
            task.update(dependencies=dependencies, dependency_attempts={dep: 1 for dep in dependencies})
            data['tasks'][key] = task
        self.q.path.write_text(json.dumps(data))
        with patch.object(self.q, 'snapshot', wraps=self.q.snapshot) as snapshot:
            health = self.q.apply('list')
        self.assertTrue(health['node-1099']['usable'])
        self.assertEqual(snapshot.call_count, 2)

    def test_missing_output_has_actionable_reason(self):
        self.add()
        self.finish(self.claim())
        (self.root / 'review/note.md').unlink()
        self.assertIn('outputs-missing-or-changed', self.q.apply('list')['read']['reasons'])


    def test_atomic_write_does_not_follow_legacy_temporary_symlink(self):
        self.add()
        victim = self.root / 'review/victim.txt'
        victim.write_text('preserve me')
        self.q.path.with_name('tasks.json.new').symlink_to(victim)
        self.claim()
        self.assertEqual(victim.read_text(), 'preserve me')

    def test_failed_atomic_write_preserves_original_and_cleans_temp(self):
        self.add()
        original = self.q.path.read_bytes()
        for replacement in ({'not-serializable': object()}, {'valid': 'json'}):
            with self.subTest(replacement=replacement):
                with patch('agent.runtime.research.storage.os.replace', side_effect=OSError('disk failure')):
                    with self.assertRaises((TypeError, OSError)):
                        write_json_atomic(self.q.path, replacement)
                self.assertEqual(original, self.q.path.read_bytes())
                self.assertEqual(list(self.q.path.parent.glob('.tasks.json.*.tmp')), [])
