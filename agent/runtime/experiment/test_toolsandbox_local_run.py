from types import SimpleNamespace

from toolsandbox_local_run import normalize_tool_call_ids


def test_normalize_tool_call_ids_preserves_payload_and_is_deterministic():
    call = SimpleNamespace(
        id="chatcmpl-tool-b1bea0269acc4ba7",
        function=SimpleNamespace(name="set_cellular_service_status", arguments='{"on": false}'),
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))]
    )

    mappings = normalize_tool_call_ids(response)

    assert mappings == [
        {
            "original": "chatcmpl-tool-b1bea0269acc4ba7",
            "normalized": call.id,
        }
    ]
    assert call.id.startswith("call_")
    assert call.id.isidentifier()
    assert call.function.name == "set_cellular_service_status"
    assert call.function.arguments == '{"on": false}'


def test_normalize_tool_call_ids_handles_no_calls():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=None))]
    )

    assert normalize_tool_call_ids(response) == []
