"""Validate current, evidence-bound Proposal acceptance; never score scientific merit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CRITERIA = (
    'problem', 'contribution', 'mechanism', 'identification',
    'feasibility', 'scope', 'independent-review',
)
REQUIRED_EVIDENCE = (
    'proposal.md', 'scope.md', 'search-log.md', 'literature/coverage.md',
    'literature/corpus.jsonl', 'proposal-audit.md',
    'literature/nearest-neighbors.md', 'proposal-depth-breadth.md',
    'novelty-review.md', 'proposal-claims.jsonl', 'proposal-rivals.jsonl',
    'proposal-threats.jsonl', 'proposal-candidates.jsonl',
)


def acceptance_errors(root: Path, proposal_id: str) -> list[str]:
    base = Path(root).resolve()
    path = base / 'proposal/acceptance.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return [f'proposal acceptance missing or invalid: {error}']
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
        return ['proposal acceptance requires version 1 object']
    errors = []
    if data.get('proposal_id') != proposal_id:
        errors.append('proposal acceptance belongs to a different Proposal ID')
    for field in ('author', 'reviewer', 'reviewed_at', 'independence_statement'):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f'proposal acceptance missing {field}')
    if str(data.get('author', '')).strip() == str(data.get('reviewer', '')).strip():
        errors.append('proposal acceptance requires a reviewer distinct from the author')
    if data.get('decision') != 'pass':
        errors.append('proposal acceptance decision must be pass')
    if data.get('open_fatal_issues') != []:
        errors.append('proposal acceptance has unresolved or undeclared fatal issues')
    snapshots = data.get('snapshots')
    if not isinstance(snapshots, dict) or not snapshots:
        return errors + ['proposal acceptance requires evidence snapshots']
    for alias in REQUIRED_EVIDENCE:
        name = (root / alias).relative_to(base).as_posix()
        if name not in snapshots:
            errors.append(f'proposal acceptance missing required snapshot: {name}')
    for name, expected in snapshots.items():
        relative = Path(name)
        if (relative.is_absolute() or '..' in relative.parts or not relative.parts
                or relative.parts[0] == 'control'
                or any((base / Path(*relative.parts[:i])).is_symlink()
                       for i in range(1, len(relative.parts) + 1))):
            errors.append(f'proposal acceptance unsafe evidence path: {name}')
            continue
        try:
            content = (base / relative).read_bytes()
            if not content or hashlib.sha256(content).hexdigest() != expected:
                errors.append(f'proposal acceptance stale evidence: {name}')
        except OSError:
            errors.append(f'proposal acceptance missing evidence: {name}')
    criteria = data.get('criteria')
    if not isinstance(criteria, dict) or set(criteria) != set(CRITERIA):
        return errors + ['proposal acceptance must assess all seven criteria']
    for name, criterion in criteria.items():
        if not isinstance(criterion, dict):
            errors.append(f'proposal acceptance invalid criterion: {name}')
            continue
        if criterion.get('status') != 'pass':
            errors.append(f'proposal acceptance criterion not passed: {name}')
        if not isinstance(criterion.get('rationale'), str) or not criterion['rationale'].strip():
            errors.append(f'proposal acceptance criterion lacks rationale: {name}')
        refs = criterion.get('evidence')
        if not isinstance(refs, list) or not refs:
            errors.append(f'proposal acceptance criterion lacks evidence: {name}')
            continue
        for ref in refs:
            if (not isinstance(ref, dict) or not isinstance(ref.get('path'), str)
                    or ref['path'] not in snapshots or not isinstance(ref.get('locator'), str)
                    or not ref['locator'].strip()):
                errors.append(f'proposal acceptance criterion has unbound evidence: {name}')
    return errors
