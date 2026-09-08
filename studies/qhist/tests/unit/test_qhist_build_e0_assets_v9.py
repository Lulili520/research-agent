import hashlib
import unittest

import qhist_build_e0_assets_v9 as builder
import qhist_v9_spec as spec


class QHistBuildAssetsV9Tests(unittest.TestCase):
    def test_contract_replaces_no_roles_and_is_hashed(self):
        episode = {
            "episode_id": "test",
            "base_messages": [
                {"role": "system", "content": "Original."},
                {"role": "user", "content": "Do the task."},
            ],
        }
        result = builder.inject_agent_contract(episode)
        self.assertEqual([row["role"] for row in result["base_messages"]], ["system", "user"])
        self.assertEqual(result["base_messages"][0]["content"].count(spec.AGENT_TOOL_CONTRACT), 1)
        self.assertEqual(
            result["agent_tool_contract"]["sha256"],
            hashlib.sha256(spec.AGENT_TOOL_CONTRACT.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(episode["base_messages"][0]["content"], "Original.")

    def test_contract_requires_one_leading_system_message(self):
        with self.assertRaises(RuntimeError):
            builder.inject_agent_contract(
                {"episode_id": "bad", "base_messages": [{"role": "user", "content": "x"}]}
            )


if __name__ == "__main__":
    unittest.main()
