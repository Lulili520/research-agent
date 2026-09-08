import json
import unittest

from qhist_precision_qualification import (
    PRECISIONS,
    canonical_sha256,
    format_candidate,
    package_version,
    parse_tool_calls,
    qualification_prompts,
)


class QHistPrecisionQualificationTests(unittest.TestCase):
    def test_catalog_has_two_fixed_distinct_prompts(self) -> None:
        prompts = qualification_prompts()
        self.assertEqual(set(prompts), {"add", "lookup"})
        self.assertNotEqual(
            canonical_sha256(prompts["add"]["tools"]),
            canonical_sha256(prompts["lookup"]["tools"]),
        )
        for item in prompts.values():
            self.assertNotEqual(item["gold"], item["alternative"])

    def test_parser_extracts_one_native_action(self) -> None:
        action = {"name": "add", "arguments": {"a": 2, "b": 3}}
        text = "<think>\n\n</think>\n" + format_candidate(action) + "<|im_end|>"
        self.assertEqual(parse_tool_calls(text), [action])

    def test_parser_rejects_malformed_or_non_object_arguments(self) -> None:
        malformed = '<tool_call>{"name":"add","arguments":</tool_call>'
        non_object = '<tool_call>{"name":"add","arguments":[2,3]}</tool_call>'
        self.assertEqual(parse_tool_calls(malformed), [])
        self.assertEqual(parse_tool_calls(non_object), [])

    def test_candidate_is_canonical_json(self) -> None:
        action = {"arguments": {"b": 3, "a": 2}, "name": "add"}
        payload = format_candidate(action).splitlines()[1]
        self.assertEqual(json.loads(payload), action)
        self.assertEqual(payload, '{"arguments":{"a":2,"b":3},"name":"add"}')

    def test_all_frozen_precision_ids_are_present(self) -> None:
        self.assertEqual(
            PRECISIONS, ("P00", "P10", "P01", "P11", "K16-shadow")
        )

    def test_package_version_returns_a_string(self) -> None:
        self.assertIsInstance(package_version("a-package-that-does-not-exist-qhist"), str)


if __name__ == "__main__":
    unittest.main()
