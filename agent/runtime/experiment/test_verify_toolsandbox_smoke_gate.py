from verify_toolsandbox_smoke_gate import evaluate_gate


def fixture():
    config = {
        "run_id": "r1",
        "protocol_version": 4,
        "scenario": "stateful",
        "gate": {
            "critical_milestones_exact": [0, 2],
            "minimum_any_milestone_similarity": 0.5,
            "minefield_similarity": 0.0,
            "minimum_native_tool_calls": 1,
            "maximum_tool_call_exceptions": 0,
        },
    }
    summary = {
        "scenario": "stateful",
        "status": "succeeded",
        "evaluation": {
            "milestone_mapping": {"0": [5, 1.0], "1": [7, 0.5], "2": [9, 1.0]},
            "similarity": 0.833333,
            "minefield_similarity": 0.0,
        },
        "native_tool_call_count": 3,
        "tool_call_exception_count": 0,
    }
    return config, summary


def test_gate_passes_at_boundaries():
    config, summary = fixture()
    result = evaluate_gate(config, summary)
    assert result["passed"] is True
    assert result["failure_reasons"] == []


def test_gate_rejects_nonexact_critical_and_tool_exception():
    config, summary = fixture()
    summary["evaluation"]["milestone_mapping"]["2"][1] = 0.99
    summary["tool_call_exception_count"] = 1
    result = evaluate_gate(config, summary)
    assert result["passed"] is False
    assert "critical_milestones_not_exact:[2]" in result["failure_reasons"]
    assert "tool_call_exception_count_failed" in result["failure_reasons"]


def test_gate_rejects_missing_or_low_milestones():
    config, summary = fixture()
    del summary["evaluation"]["milestone_mapping"]["2"]
    summary["evaluation"]["milestone_mapping"]["1"][1] = 0.49
    result = evaluate_gate(config, summary)
    assert result["passed"] is False
    assert "missing_critical_milestones:[2]" in result["failure_reasons"]
    assert "minimum_milestone_similarity_failed" in result["failure_reasons"]
