import unittest

from qhist_render_stimuli import choose_neutral_pair, render_authority


class QHistRenderStimuliTests(unittest.TestCase):
    def test_authority_renderer_does_not_expose_condition(self) -> None:
        text = render_authority("phone_number", "+12025550123")
        self.assertIn("phone number", text)
        self.assertNotIn("C_text", text)

    def test_neutral_pair_is_distinct_and_within_two_tokens(self) -> None:
        # 简化 tokenizer 足以检验选择器的约束逻辑。
        count = lambda value: len(value.replace('"', "").split())
        target = count(render_authority("phone number", "+12025550123"))
        first, second = choose_neutral_pair(target, count)
        self.assertNotEqual(first[:2], second[:2])
        self.assertLessEqual(abs(first[2] - target), 2)
        self.assertLessEqual(abs(second[2] - target), 2)
        self.assertLessEqual(abs(first[2] - second[2]), 2)


if __name__ == "__main__":
    unittest.main()
