import unittest

from qhist_toolsandbox_gate import leaf_differences


class QHistToolSandboxGateTests(unittest.TestCase):
    def test_leaf_differences_finds_exact_nested_field(self) -> None:
        truth = [{"id": 1, "value": "a"}]
        false = [{"id": 1, "value": "b"}]
        self.assertEqual(leaf_differences(truth, false), ["[0].value"])

    def test_leaf_differences_detects_no_change(self) -> None:
        self.assertEqual(leaf_differences({"a": True}, {"a": True}), [])


if __name__ == "__main__":
    unittest.main()
