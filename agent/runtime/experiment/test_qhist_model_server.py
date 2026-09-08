import unittest

from qhist_model_server import visible_content


class QHistModelServerTests(unittest.TestCase):
    def test_visible_content_strips_qwen_wrappers(self) -> None:
        self.assertEqual(
            visible_content("<think>\n\n</think>\nFinished.<|im_end|>"),
            "Finished.",
        )


if __name__ == "__main__":
    unittest.main()
