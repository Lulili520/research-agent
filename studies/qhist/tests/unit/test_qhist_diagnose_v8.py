import unittest

from qhist_diagnose_v8 import classify_decision, syntactically_valid


class QHistV8DiagnosisTests(unittest.TestCase):
    def test_plain_terminal_text_is_valid_syntax(self) -> None:
        decision = {
            "valid_native_tool_action": False,
            "parsed_actions": [],
            "visible_content": "The task is complete.",
        }
        output_class = classify_decision(decision)
        self.assertEqual(output_class, "terminal-text")
        self.assertTrue(syntactically_valid(output_class))

    def test_malformed_tool_attempt_is_not_terminal_text(self) -> None:
        decision = {
            "valid_native_tool_action": False,
            "parsed_actions": [],
            "visible_content": '<tool_call>{"name": "x"}',
        }
        output_class = classify_decision(decision)
        self.assertEqual(output_class, "malformed-tool-attempt")
        self.assertFalse(syntactically_valid(output_class))

    def test_parsed_but_rejected_action_is_invalid_native(self) -> None:
        decision = {
            "valid_native_tool_action": False,
            "parsed_actions": [{"name": "unknown", "arguments": {}}],
            "visible_content": "",
        }
        output_class = classify_decision(decision)
        self.assertEqual(output_class, "invalid-native-tool")
        self.assertFalse(syntactically_valid(output_class))


if __name__ == "__main__":
    unittest.main()
