"""Different research questions use the same controller without topic-specific code."""
import json

import pytest
import test_researchctl as fixtures
from agent.runtime.research import gates


@pytest.mark.parametrize('topic,research_type,materials', [
    ('Compiler register allocation', 'algorithm', {
        'mode': 'generated', 'rationale': 'generate programs with fixed seeds and sizes'}),
    ('Distributed storage consistency', 'system', {
        'mode': 'external', 'sources': [{'url': 'https://example.org/workload',
                                        'version': 'fixture-v1', 'selection': 'fixed workload subset'}]}),
    ('Combinatorial lower bounds', 'theory', {
        'mode': 'none', 'rationale': 'formal derivation and counterexample search; no dataset required'}),
])
def test_protocol_is_driven_by_project_scope(topic, research_type, materials):
    case = fixtures.ResearchControlTests()
    case.TOPIC = topic
    case.RESEARCH_TYPE = research_type
    case.setUp()
    try:
        case.advance_to_protocol()
        case.write_protocol_artifacts()
        path = case.internal / 'experiments/design.json'
        design = json.loads(path.read_text())
        design['research_materials'] = materials
        design['resource_budget'] = {'gpu_hours': 0, 'cpu_hours': 1}
        path.write_text(json.dumps(design))
        assert gates.protocol_errors(case.internal) == []
        case.invoke('freeze-protocol', str(case.root))
        result = json.loads(case.invoke('status', str(case.root)).stdout)
        assert result['research']['topic'] == topic
        assert result['research']['research_type'] == research_type
        assert result['state']['empirical_status'] == 'not-run'
    finally:
        case.tearDown()
