import unittest

import qhist_trajectory_batch_v9 as runner


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_id": {"type": "string"},
                    "mode": {"type": "string", "enum": ["fast", "safe"]},
                },
                "required": ["record_id"],
                "additionalProperties": False,
            },
        },
    }
]


def generated(raw, visible=None):
    return {"raw_text": raw, "visible_content": raw if visible is None else visible}


class QHistTrajectoryV9Tests(unittest.TestCase):
    def test_valid_native_call(self):
        result = runner.classify_generated_reply(
            generated('<tool_call>{"name":"lookup","arguments":{"record_id":"x","mode":"safe"}}</tool_call>'),
            TOOLS,
            0,
        )
        self.assertEqual(result["output_class"], "native-tool")
        self.assertTrue(result["syntax_valid"])

    def test_reply_level_schema_failure(self):
        raw = (
            '<tool_call>{"name":"lookup","arguments":{"record_id":"x"}}</tool_call>'
            '<tool_call>{"name":"lookup","arguments":{"record_id":"y","extra":1}}</tool_call>'
        )
        result = runner.classify_generated_reply(generated(raw), TOOLS, 0)
        self.assertEqual(result["output_class"], "invalid-native-tool")
        self.assertEqual(result["actions"], [])
        self.assertTrue(any("additional-property" in item for item in result["validation_failures"]))

    def test_malformed_and_terminal_are_distinct(self):
        malformed = runner.classify_generated_reply(
            generated('<tool_call>{"name":</tool_call>'), TOOLS, 0
        )
        terminal = runner.classify_generated_reply(
            generated("The task is complete."), TOOLS, 0
        )
        empty = runner.classify_generated_reply(generated("", ""), TOOLS, 0)
        wrapped_empty = runner.classify_generated_reply(
            generated("<|im_end|>", ""), TOOLS, 0
        )
        self.assertEqual(malformed["output_class"], "malformed-tool-attempt")
        self.assertEqual(terminal["output_class"], "terminal-text")
        self.assertTrue(terminal["syntax_valid"])
        self.assertEqual(empty["output_class"], "empty")
        self.assertEqual(wrapped_empty["output_class"], "empty")

    def test_tool_cap_is_fail_closed(self):
        result = runner.classify_generated_reply(
            generated('<tool_call>{"name":"lookup","arguments":{"record_id":"x"}}</tool_call>'),
            TOOLS,
            16,
        )
        self.assertEqual(result["output_class"], "invalid-native-tool")
        self.assertEqual(result["actions"], [])

    def test_unknown_tool_is_fail_closed(self):
        result = runner.classify_generated_reply(
            generated('<tool_call>{"name":"missing","arguments":{}}</tool_call>'),
            TOOLS,
            0,
        )
        self.assertEqual(result["output_class"], "invalid-native-tool")
        self.assertEqual(result["actions"], [])
        self.assertTrue(any("unknown-tool" in item for item in result["validation_failures"]))


if __name__ == "__main__":
    unittest.main()
