"""Adversarial workflow regressions using only temporary projects and fake run artifacts."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent.runtime.research import test_researchctl as fixtures
from agent.runtime.research import researchctl as ctl
from agent.runtime.research.audit import Audit


@pytest.fixture
def project():
    case = fixtures.ResearchControlTests()
    case.setUp()
    try:
        case.advance_to_protocol()
        case.write_protocol_artifacts()
        (case.internal / 'proposal/novelty-refresh-pre-experiment.md').write_text(
            'Search date: 2026-09-08\nDatabases: proceedings\nQuery families: nearest\n'
            'New nearest neighbors: none\nClaim impact: unchanged\nRefresh decision: pass\n')
        case.invoke('freeze-protocol', str(case.root))
        yield case
    finally:
        case.tearDown()


def enter_pilot(case):
    case.grant_execution()
    case.invoke('transition', str(case.root), 'pilot', '--reason', 'authorized pilot')
    case.invoke('register-experiment', str(case.root), '--id', 'E1', '--purpose', 'pilot measurement')


def register(case, run_id):
    path = case.internal / f'runs/{run_id}.config.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text('{"seed": 1}')
    return case.invoke('register-run', str(case.root), '--id', run_id, '--experiment', 'E1',
                       '--config', f'runs/{run_id}.config.json', '--code-revision', 'test',
                       '--environment', 'test', ok=False)


def finish(case, run_id, status='succeeded'):
    path = case.internal / f'runs/{run_id}.result.json'
    path.write_text('{"result": "synthetic fixture"}')
    case.invoke('finish-run', str(case.root), '--id', run_id, '--status', status,
                '--artifact', f'runs/{run_id}.result.json', '--reason', 'fixture')


def pilot_gate(case, ids):
    (case.internal / 'experiments/pilot.md').write_text('Pilot gate: pass\n')
    (case.internal / 'experiments/pilot-gate.json').write_text(json.dumps({
        'decision': 'pass', 'protocol_version': 1, 'run_ids': ids,
        'reviewer': 'independent-pilot-reviewer', 'rationale': 'measurement and cost checked',
    }))


def advance_main(case, ok=True):
    return case.invoke('transition', str(case.root), 'main-experiment', '--reason', 'pilot reviewed', ok=ok)


@pytest.mark.parametrize('name', ctl.BUNDLE_FILES)
def test_every_frozen_file_is_checked(project, name):
    path = project.internal / name
    path.write_text(path.read_text() + '\nchanged after freeze\n')
    with pytest.raises(SystemExit, match='changed after freezing'):
        ctl.verify_protocol(project.internal)


def test_missing_lock_fails_shared_gate_and_audit(project):
    enter_pilot(project)
    (project.internal / 'experiments/protocol.lock.json').unlink()
    assert any('protocol.lock' in e or 'freeze the protocol' in e for e in ctl.stage_errors(project.internal, 'pilot'))
    audit = Audit(project.root)
    audit.iterative()
    assert any('protocol.lock' in e or 'freeze the protocol' in e for e in audit.errors)


def test_execution_requires_grant_and_rechecks_revocation(project):
    denied = project.invoke('transition', str(project.root), 'pilot', '--reason', 'no grant', ok=False)
    assert denied.returncode != 0 and 'authorization required' in denied.stderr
    enter_pilot(project)
    project.invoke('authorize-execution', str(project.root), 'false', '--evidence',
                   'control/user-execution.md', '--reason', 'user revoked')
    denied = register(project, 'R1')
    assert denied.returncode != 0 and 'authorization required' in denied.stderr


def test_default_permission_cannot_bypass_frozen_requirements(project):
    # New protocol explicitly needs external_compute. No resource permission has been granted.
    bump_protocol(project, required_permissions=['external_compute'])
    denied = project.invoke('authorize-execution', str(project.root), 'true', '--evidence',
                            'control/user-execution.md', '--reason', 'request', ok=False)
    assert denied.returncode != 0 and 'permission not authorized' in denied.stderr


def bump_protocol(case, **updates):
    (case.internal / 'control/user-execution.md').write_text('Explicit user instruction.')
    for name in ['experiments/protocol.md', 'experiments/protocol-audit.md']:
        path = case.internal / name
        path.write_text(path.read_text().replace('Protocol version: 1', 'Protocol version: 2'))
    path = case.internal / 'experiments/design.json'
    design = json.loads(path.read_text())
    design.update(protocol_version=2, **updates)
    path.write_text(json.dumps(design))
    case.invoke('freeze-protocol', str(case.root))


def test_new_bundle_invalidates_old_authorization(project):
    project.grant_execution()
    bump_protocol(project)
    with pytest.raises(SystemExit, match='different protocol bundle'):
        ctl.verify_execution_authorization(project.internal)


def test_empirical_status_requires_artifacts_and_pilot_gate_requires_real_runs(project):
    enter_pilot(project)
    assert json.loads((project.internal / 'state.json').read_text())['empirical_status'] == 'not-run'
    pilot_gate(project, ['invented'])
    assert advance_main(project, ok=False).returncode != 0
    assert register(project, 'pilot-1').returncode == 0
    pilot_gate(project, ['pilot-1'])
    assert advance_main(project, ok=False).returncode != 0  # still queued
    finish(project, 'pilot-1')
    assert json.loads((project.internal / 'state.json').read_text())['empirical_status'] == 'pilot'
    advance_main(project)
    assert json.loads((project.internal / 'state.json').read_text())['empirical_status'] == 'pilot'
    assert register(project, 'main-1').returncode == 0
    assert ctl.stage_errors(project.internal, 'main-experiment') == []
    finish(project, 'main-1', status='failed')  # failed execution with logs remains evidence
    assert json.loads((project.internal / 'state.json').read_text())['empirical_status'] == 'tested'
    project.invoke('transition', str(project.root), 'experiment-protocol', '--reason', 'review failure')
    assert json.loads((project.internal / 'state.json').read_text())['empirical_status'] == 'tested'


def test_modified_result_is_rejected(project):
    enter_pilot(project)
    assert register(project, 'pilot-1').returncode == 0
    finish(project, 'pilot-1')
    pilot_gate(project, ['pilot-1'])
    (project.internal / 'runs/pilot-1.result.json').write_text('{"result": "edited"}')
    denied = advance_main(project, ok=False)
    assert denied.returncode != 0 and 'artifact changed' in denied.stderr


def test_cancelled_run_does_not_create_empirical_progress(project):
    enter_pilot(project)
    assert register(project, 'cancelled').returncode == 0
    project.invoke('finish-run', str(project.root), '--id', 'cancelled', '--status', 'cancelled', '--reason', 'never started')
    assert ctl.empirical_status(project.internal) == 'not-run'


def test_blocked_cannot_jump_over_gates(project):
    project.invoke('transition', str(project.root), 'blocked', '--reason', 'pause')
    denied = project.invoke('transition', str(project.root), 'main-experiment', '--reason', 'skip', ok=False)
    assert denied.returncode != 0 and 'recorded stage' in denied.stderr
    project.invoke('transition', str(project.root), 'experiment-protocol', '--reason', 'resume')


def test_migration_preserves_old_lock_and_requires_new_freeze(project):
    enter_pilot(project)
    old = (project.internal / 'experiments/protocol.lock.json').read_bytes()
    project.invoke('migrate-policy', str(project.root), '--reason', 'upgrade')
    assert any(p.read_bytes() == old for p in (project.internal / 'control/migrations').glob('protocol-lock-*.json'))
    state = json.loads((project.internal / 'state.json').read_text())
    assert state['research_stage'] == 'experiment-protocol'
    project.invoke('revalidate-policy', str(project.root))
    assert project.invoke('transition', str(project.root), 'pilot', '--reason', 'no refreeze', ok=False).returncode != 0


def test_protocol_does_not_require_topic_specific_sections_or_dataset_count(project):
    path = project.root / 'outputs/03-理论分析与实验探究.md'
    path.write_text(path.read_text().replace('https://a.example https://b.example https://c.example', ''))
    assert ctl.protocol_errors(project.internal) == []
    design_path = project.internal / 'experiments/design.json'
    design = json.loads(design_path.read_text())
    design['research_materials'] = {'mode': 'external', 'sources': [
        {'url': 'https://example.org/dataset', 'version': 'v1', 'selection': 'test split, 50 samples'}]}
    design_path.write_text(json.dumps(design))
    assert ctl.protocol_errors(project.internal) == []
    design['research_materials']['sources'][0].pop('version')
    design_path.write_text(json.dumps(design))
    assert any('fixed version' in e for e in ctl.protocol_errors(project.internal))


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf'])
def test_budget_rejects_nonfinite(value):
    with pytest.raises(SystemExit, match='finite'):
        ctl.nonnegative('cost', float(value))
