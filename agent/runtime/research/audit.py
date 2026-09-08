#!/usr/bin/env python3
"""Cross-platform, read-only research artifact audit (Python standard library)."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re

try:
    from . import researchctl as ctl
except ImportError:
    import researchctl as ctl


class Audit:
    def __init__(self, topic: Path):
        self.topic = topic
        self.base = topic / '.research' if (topic / '.research').is_dir() else topic
        self.root = ctl.ResearchRoot(self.base)
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def read(self, name: str) -> str:
        path = self.root / name
        if name == 'report.md' and not path.is_file():
            path = self.topic / 'outputs/01-文献调研总结.md'
        try:
            text = path.read_text(encoding='utf-8-sig')
            if not text.strip():
                self.errors.append(f'empty artifact: {name}')
            return text
        except (OSError, UnicodeError) as error:
            self.errors.append(f'cannot read {name}: {error}')
            return ''

    def fields(self, name: str, text: str, fields: tuple[str, ...]) -> None:
        for field in fields:
            if field.casefold() not in text.casefold():
                self.errors.append(f'{name} missing field: {field}')

    def check(self, function, *, returns_errors: bool = True) -> None:
        try:
            errors = function(self.root)
            if returns_errors and errors:
                self.errors.extend(errors)
        except (SystemExit, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            self.errors.append(f'{function.__name__}: {error}')

    def review(self) -> None:
        state, search, literature, evidence, report = [self.read(n) for n in
            ('state.md', 'search-log.md', 'literature.md', 'evidence.md', 'report.md')]
        self.fields('state.md', state, ('Workflow status:', 'Novelty status:', 'Search cutoff:', 'Last updated:'))
        def dates(text):
            result = []
            for value in re.findall(r'\b20\d{2}-\d{2}-\d{2}\b', text):
                try:
                    result.append(date.fromisoformat(value))
                except ValueError:
                    pass
            return result
        state_dates, artifact_dates = dates(state), dates(search + '\n' + evidence + '\n' + report)
        if state_dates and artifact_dates and max(state_dates) < max(artifact_dates):
            self.errors.append('state.md is older than another core artifact')
        for name, text in [('search-log.md', search), ('literature.md', literature)]:
            if not re.search(r'https?://', text):
                self.warnings.append(f'{name} contains no stable links')
        if search and not re.search(r'query|search|查询|检索', search, re.I):
            self.errors.append('search-log.md does not expose queries/search activity')
        if search and not dates(search):
            self.errors.append('search-log.md has no valid run/update date')
        claims = set(re.findall(r'\bC\d+\b', evidence))
        if not claims:
            self.errors.append('evidence.md contains no stable claim IDs')
        elif not claims.intersection(re.findall(r'\bC\d+\b', report)):
            self.warnings.append('report.md does not expose claim-ID traceability')
        if re.search(r'Novelty status:\s*provisional', state, re.I) and not re.search(
            r'novelty status remains provisional', search, re.I
        ):
            self.errors.append('provisional novelty lacks a dated/scoped bounded statement')
        if re.search(r'Workflow status:\s*complete', state, re.I) and self.errors:
            self.errors.append('state claims workflow completion while audit errors remain')

    def iterative(self) -> None:
        texts = {n: self.read(n) for n in
                 ('research.json', 'state.json', 'events.jsonl', 'decisions.jsonl', 'state.md')}
        # The decision log can be empty before the first decision; init emits an event.
        self.errors = [e for e in self.errors if e not in
                       ('empty artifact: decisions.jsonl',)]
        try:
            config = json.loads(texts['research.json'])
            state = json.loads(texts['state.json'])
            if not isinstance(config, dict) or not isinstance(state, dict):
                raise ValueError('project and state must be JSON objects')
        except ValueError as error:
            self.errors.append(f'invalid machine state JSON: {error}')
            return
        self.fields('state.md', texts['state.md'], (
            'Workflow status:', 'Research stage:', 'Proposal decision:', 'Novelty status:',
            'Empirical status:', 'Execution readiness:', 'Iteration:', 'Last updated:'))
        for field in ('proposal_decision', 'novelty_status', 'empirical_status', 'execution_readiness'):
            if field not in state:
                self.errors.append(f'state.json missing independent research status: {field}')
        self.check(ctl.verify_events)
        self.check(ctl.require_current_policy)
        stage = state.get('research_stage')
        if stage not in ctl.STAGES:
            self.errors.append(f'invalid research stage: {stage}')
            return
        stages = ctl.STAGES[:ctl.STAGES.index('complete') + 1]
        for first, check in [('literature-mapping', ctl.scope_errors),
                             ('theory-building', ctl.proposal_errors),
                             ('experiment-protocol', ctl.theory_errors)]:
            if stage in stages[stages.index(first):]:
                self.check(check)
        if (self.root / 'experiments/protocol.lock.json').is_file():
            self.check(ctl.protocol_errors)
            self.check(ctl.verify_protocol, returns_errors=False)
        if state.get('workflow_status') == 'complete' or stage == 'complete':
            if stage != 'complete' or state.get('workflow_status') != 'complete':
                self.errors.append('workflow status and research stage disagree on completion')
            self.check(ctl.completion_errors)
            for name, fields in [
                ('theory.md', ('Assumptions:', 'Competing explanations:', 'Predictions:',
                               'Falsifiers:', 'Experiment mapping:')),
                ('experiments/protocol.md', ('Claims:', 'Independent variables:',
                    'Dependent variables:', 'Controls:', 'Baselines:', 'Metrics:',
                    'Randomness:', 'Stopping rules:')),
            ]:
                self.fields(name, self.read(name), fields)
            for name, pattern in [
                ('experiments/registry.jsonl', r'experiment_id'),
                ('runs/registry.jsonl', r'run_id'), ('runs/outcomes.jsonl', r'status'),
                ('paper/claims.jsonl', r'claim_id'), ('paper/iterations.jsonl', r'cycle_type'),
                ('search-log.md', r'(?is)(?=.*(?:query|search))(?=.*20\d{2}-\d{2}-\d{2})'),
            ]:
                text = self.read(name)
                if text and not re.search(pattern, text, re.I):
                    self.errors.append(f'{name} lacks required audit identifiers or dates')
            if self.errors:
                self.errors.append('machine state claims completion while audit errors remain')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('review', 'iterative'))
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    if not args.directory.is_dir():
        print(f'ERROR: topic directory does not exist: {args.directory}')
        return 2
    topic = args.directory.resolve()
    if topic.name == '.research':
        topic = topic.parent
    audit = Audit(topic)
    getattr(audit, 'review' if args.mode == 'review' else 'iterative')()
    for warning in audit.warnings:
        print(f'WARNING: {warning}')
    for error in audit.errors:
        print(f'ERROR: {error}')
    print(f'Audit summary: {len(audit.errors)} error(s), {len(audit.warnings)} warning(s)')
    return int(bool(audit.errors))


if __name__ == '__main__':
    raise SystemExit(main())
