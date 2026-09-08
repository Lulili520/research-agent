"""Protocol bundles, version-bound execution grants, and verifiable run evidence."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

try:
    from .storage import read_json, read_jsonl, load_events, verify_events
    from .policy import PERMISSIONS
except ImportError:
    from storage import read_json, read_jsonl, load_events, verify_events
    from policy import PERMISSIONS

BUNDLE_FILES = (
    'experiments/protocol.md', 'experiments/design.json',
    'experiments/analysis-plan.md', 'experiments/protocol-audit.md',
    'scope.md', 'proposal.md', 'theory.md',
    'theory/claims.jsonl', 'theory/predictions.jsonl',
)
TERMINAL_STATUSES = {'succeeded', 'failed', 'timed-out', 'cancelled', 'invalid'}
OBSERVED_STATUSES = {'succeeded', 'failed', 'timed-out'}


def artifact_path(root, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise SystemExit(f'artifact must be a relative project path: {relative}')
    base = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(base) or not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f'missing, empty or out-of-project artifact: {relative}')
    return path


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def artifact_files(root, relative: str) -> dict[str, str]:
    """Hash a file and recursively verify project-relative manifest members.

    Manifests use {"manifest_schema": 1, "files_sha256": {path: sha256}}.
    Reserved manifest filenames cannot silently fall back to opaque files.
    """
    result = {}
    visiting = set()

    def visit(name):
        path = artifact_path(root, name)
        if path in visiting:
            raise SystemExit(f'cyclic artifact manifest: {name}')
        if name in result:
            return
        result[name] = digest(path)
        reserved = path.name == 'manifest.json' or path.name.endswith('.manifest.json')
        try:
            data = json.loads(path.read_text(encoding='utf-8')) if path.suffix == '.json' else None
        except (ValueError, UnicodeError):
            data = None
        is_manifest = isinstance(data, dict) and ('manifest_schema' in data or 'files_sha256' in data)
        if not reserved and not is_manifest:
            return
        if not isinstance(data, dict) or data.get('manifest_schema') != 1 or not isinstance(data.get('files_sha256'), dict) or not data['files_sha256']:
            raise SystemExit(f'invalid artifact manifest: {name}')
        visiting.add(path)
        for member, expected in data['files_sha256'].items():
            if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
                raise SystemExit(f'invalid manifest member hash: {member}')
            if digest(artifact_path(root, member)) != expected:
                raise SystemExit(f'artifact manifest member changed: {member}')
            visit(member)
        visiting.remove(path)

    visit(relative)
    return result


def manifest_digest(files: dict) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bundle_files(root) -> dict[str, str]:
    return {name: digest(artifact_path(root, name)) for name in BUNDLE_FILES}


def verify_protocol(root) -> dict:
    path = root / 'experiments/protocol.lock.json'
    if not path.is_file():
        raise SystemExit('freeze the protocol before registering experiments or runs')
    lock = read_json(path)
    if lock.get('lock_schema') != 2 or set(lock.get('files_sha256', {})) != set(BUNDLE_FILES):
        raise SystemExit('legacy or incomplete protocol lock; migrate policy and freeze a new bundle')
    if lock.get('bundle_sha256') != manifest_digest(lock['files_sha256']):
        raise SystemExit('protocol bundle manifest digest mismatch')
    state = read_json(root / 'state.json')
    if state.get('protocol_version') != lock.get('version'):
        raise SystemExit('protocol lock version differs from machine state')
    for name, expected in lock['files_sha256'].items():
        if digest(artifact_path(root, name)) != expected:
            raise SystemExit(f'{name} changed after freezing; freeze a new version before continuing')
        archived = artifact_path(root, f'experiments/protocols/v{lock["version"]:03d}.bundle/{name}')
        if digest(archived) != expected:
            raise SystemExit(f'archived protocol bundle changed: {name}')
    if digest(artifact_path(root, lock['archive'])) != lock.get('archive_sha256'):
        raise SystemExit('archived protocol text changed')
    archive_lock = read_json(root / f'experiments/protocols/v{lock["version"]:03d}.lock.json')
    if archive_lock != lock:
        raise SystemExit('current protocol lock differs from archived lock')
    verify_events(root)
    frozen = [e['payload'] for e in load_events(root) if e['type'] == 'protocol-frozen']
    if not frozen or frozen[-1] != lock:
        raise SystemExit('protocol lock differs from protocol-frozen event')
    return lock


def required_permissions(root) -> list[str]:
    value = read_json(root / 'experiments/design.json').get('required_permissions')
    if not isinstance(value, list) or any(p not in PERMISSIONS for p in value):
        raise SystemExit('design.json must declare required_permissions as a list of known permissions')
    return value


def verify_execution_authorization(root) -> dict:
    lock = verify_protocol(root)
    grants = [e['payload'] for e in load_events(root) if e['type'] == 'execution-authorized']
    if not grants or not grants[-1].get('granted'):
        raise SystemExit('explicit execution authorization required; use authorize-execution with user evidence')
    grant = grants[-1]
    if grant.get('protocol_version') != lock['version'] or grant.get('bundle_sha256') != lock['bundle_sha256']:
        raise SystemExit('execution authorization belongs to a different protocol bundle')
    if digest(artifact_path(root, grant['evidence'])) != grant['evidence_sha256']:
        raise SystemExit('execution authorization evidence changed')
    config = read_json(root / 'research.json')
    for permission in required_permissions(root):
        if not config['permissions'].get(permission, False):
            raise SystemExit(f'permission not authorized: {permission}')
    return grant


def verified_outcomes(root, *, require_terminal: bool = False) -> list[tuple[dict, dict]]:
    verify_events(root)
    runs = read_jsonl(root / 'runs/registry.jsonl')
    outcomes = read_jsonl(root / 'runs/outcomes.jsonl')
    events = load_events(root)
    for kind, records in [('run-registered', runs), ('run-finished', outcomes)]:
        event_records = [e['payload'] for e in events if e['type'] == kind]
        # Older registrations used partial events; preserve them without treating
        # them as current scientific evidence. Full records must match both ways.
        full_events = [r for r in event_records if kind == 'run-finished' or r.get('record_schema') == 2]
        for record in full_events:
            if records.count(record) != 1 or full_events.count(record) != 1:
                raise SystemExit(f'{kind} event differs from registry: {record.get("run_id")}')
    by_id = {}
    for run in runs:
        run_id = run.get('run_id')
        if not run_id or run_id in by_id:
            raise SystemExit('missing or duplicate registered run ID')
        if run.get('record_schema') == 2 and not any(
            e['type'] == 'run-registered' and e['payload'] == run for e in events
        ):
            raise SystemExit(f'run registration differs from event record: {run_id}')
        by_id[run_id] = run
    seen = set()
    verified = []
    for outcome in outcomes:
        run_id = outcome.get('run_id')
        if run_id not in by_id or run_id in seen:
            raise SystemExit(f'unknown or duplicate run outcome: {run_id}')
        seen.add(run_id)
        run = by_id[run_id]
        if run.get('record_schema') == 2 and not any(
            e['type'] == 'run-finished' and e['payload'] == outcome for e in events
        ):
            raise SystemExit(f'run outcome differs from event record: {run_id}')
        if outcome.get('status') not in TERMINAL_STATUSES:
            raise SystemExit(f'invalid terminal run status: {run_id}')
        if outcome['status'] not in {'invalid', 'cancelled'} and digest(artifact_path(root, run['config'])) != run.get('config_sha256'):
            raise SystemExit(f'run config changed: {run_id}')
        if outcome.get('artifact'):
            files = artifact_files(root, outcome['artifact'])
            if files[outcome['artifact']] != outcome.get('artifact_sha256'):
                raise SystemExit(f'run artifact changed: {run_id}')
            if outcome.get('artifact_files_sha256') is not None and files != outcome['artifact_files_sha256']:
                raise SystemExit(f'run artifact members changed: {run_id}')
        elif outcome['status'] == 'succeeded':
            raise SystemExit(f'succeeded run lacks artifact: {run_id}')
        verified.append((run, outcome))
    if require_terminal and set(by_id) != seen:
        raise SystemExit('registered runs lack terminal outcomes')
    return verified


def empirical_status(root) -> str:
    result = 'not-run'
    for run, outcome in verified_outcomes(root):
        if run.get('record_schema') != 2:
            continue
        if outcome['status'] not in OBSERVED_STATUSES or not outcome.get('artifact'):
            continue
        if run.get('stage') in {'main-experiment', 'robustness-analysis'}:
            return 'tested'
        if run.get('stage') == 'pilot':
            result = 'pilot'
    return result


def require_stage_terminal(root, stage: str, version: int, pairs: list) -> None:
    completed = {run['run_id'] for run, _ in pairs}
    pending = [run['run_id'] for run in read_jsonl(root / 'runs/registry.jsonl')
               if run.get('stage') == stage and run.get('protocol_version') == version
               and run['run_id'] not in completed]
    if pending:
        raise SystemExit(f'{stage} runs lack terminal outcomes: {pending}')


def require_pilot_evidence(root) -> None:
    lock = verify_protocol(root)
    gate = read_json(artifact_path(root, 'experiments/pilot-gate.json'))
    if gate.get('decision') != 'pass' or gate.get('protocol_version') != lock['version']:
        raise SystemExit('pilot gate must pass for the current protocol version')
    if not str(gate.get('reviewer', '')).strip() or not str(gate.get('rationale', '')).strip():
        raise SystemExit('pilot gate requires reviewer and rationale')
    ids = gate.get('run_ids')
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
        raise SystemExit('pilot gate requires distinct run_ids')
    pairs = verified_outcomes(root)
    require_stage_terminal(root, 'pilot', lock['version'], pairs)
    eligible = {run['run_id'] for run, outcome in pairs
                if run.get('record_schema') == 2 and run.get('stage') == 'pilot' and run.get('protocol_version') == lock['version']
                and run.get('bundle_sha256') == lock['bundle_sha256']
                and outcome['status'] == 'succeeded' and outcome.get('artifact')}
    if not set(ids) <= eligible:
        raise SystemExit('pilot gate references missing, unsuccessful or stale pilot run evidence')


def require_main_evidence(root) -> None:
    lock = verify_protocol(root)
    pairs = verified_outcomes(root)
    require_stage_terminal(root, 'main-experiment', lock['version'], pairs)
    if not any(run.get('record_schema') == 2 and run.get('stage') == 'main-experiment' and run.get('protocol_version') == lock['version']
               and run.get('bundle_sha256') == lock['bundle_sha256']
               and outcome['status'] in OBSERVED_STATUSES and outcome.get('artifact')
               for run, outcome in pairs):
        raise SystemExit('main experiment requires terminal evidence for the current protocol')
