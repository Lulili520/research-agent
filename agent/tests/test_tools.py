import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import parse_qs, urlparse

from agent.runtime.research.audit import Audit
from agent.runtime.research.collect_openalex import load_queries, fetch

REPO = Path(__file__).resolve().parents[2]


class ToolTests(unittest.TestCase):
    def test_review_accepts_public_report_and_detects_stale_state(self):
        with tempfile.TemporaryDirectory() as d:
            topic = Path(d)
            audit = Audit(topic)
            contents = {
                'state.md': 'Workflow status: complete\nNovelty status: audited\nSearch cutoff: 2026-09-01\nLast updated: 2026-09-01',
                'search-log.md': 'Query: test 2026-09-01 https://example.org',
                'literature.md': 'https://example.org/paper',
                'evidence.md': 'C1 reported 2026-09-01',
            }
            for name, text in contents.items():
                path = audit.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            (topic / 'outputs').mkdir()
            report = topic / 'outputs/01-文献调研总结.md'
            report.write_text('C1 reported 2026-09-01')
            audit.review()
            self.assertEqual(audit.errors, [])
            report.write_text('C1 reported 2026-09-02')
            audit = Audit(topic)
            audit.review()
            self.assertTrue(any('older' in e for e in audit.errors))

    def test_iterative_audit_rejects_tampering_and_false_completion(self):
        with tempfile.TemporaryDirectory() as d:
            topic = Path(d) / 'topic'
            subprocess.run([sys.executable, str(REPO / 'agent/runtime/research/researchctl.py'),
                            'init', str(topic), '--topic', 'test', '--research-type', 'benchmark'],
                           check=True, capture_output=True)
            audit = Audit(topic)
            (audit.root / 'state.md').write_text(
                'Workflow status: in-progress\nResearch stage: initialized\n'
                'Proposal decision: revise\nNovelty status: exploratory\n'
                'Empirical status: not-run\nExecution readiness: designed\n'
                'Iteration: 0\nLast updated: 2026-09-08\n')
            audit.iterative()
            self.assertEqual(audit.errors, [])
            events = audit.root / 'events.jsonl'
            entries = [json.loads(line) for line in events.read_text().splitlines()]
            entries[0]['actor'] = 'tampered'
            events.write_text('\n'.join(json.dumps(e) for e in entries) + '\n')
            audit = Audit(topic)
            audit.iterative()
            self.assertTrue(any('verify_events: event log integrity failure' in e for e in audit.errors))
            state_path = audit.root / 'state.json'
            state = json.loads(state_path.read_text())
            state.update(research_stage='complete', workflow_status='complete')
            state_path.write_text(json.dumps(state))
            audit = Audit(topic)
            audit.iterative()
            self.assertTrue(any('missing' in e for e in audit.errors))

    def test_queries_are_caller_supplied_and_validated(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'queries.json'
            path.write_text('{"systems": "distributed consensus"}')
            self.assertEqual(load_queries(path), {'systems': 'distributed consensus'})
            for content in ['{}', '[]', '{"x": 3}', '{"x": " "}']:
                path.write_text(content)
                with self.assertRaises(ValueError):
                    load_queries(path)

    def test_fetch_uses_requested_scope(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"results": [{"id": "W1"}]}'
        with patch('urllib.request.urlopen', return_value=response) as open_url:
            self.assertEqual(fetch('distributed consensus', 7, 'test@example.org', '2024-01-01'),
                             [{'id': 'W1'}])
        query = parse_qs(urlparse(open_url.call_args.args[0].full_url).query)
        self.assertEqual(query['search'], ['distributed consensus'])
        self.assertEqual(query['filter'], ['from_publication_date:2024-01-01'])
        self.assertEqual(query['per-page'], ['7'])

    def test_agent_has_no_topic_imports(self):
        for path in (REPO / 'agent/runtime').rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or '']
                allowed = sys.stdlib_module_names | {'agent'} | {p.stem for p in (REPO / 'agent/runtime/research').glob('*.py')}
                self.assertTrue(all(not m or m.split('.')[0] in allowed for m in modules), path)


if __name__ == '__main__':
    unittest.main()
