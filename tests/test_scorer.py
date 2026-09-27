import shutil
import unittest

import harness
from scorer import score_task, summarize


TASK = {
    "id": "score-test",
    "tier": 1,
    "instruction": "Delete the second line.",
    "start": "alpha\nbeta\ngamma\n",
    "target": "alpha\ngamma\n",
    "reference": "jdd:wq<CR>",
}


@unittest.skipUnless(shutil.which(harness.VIM_BIN), f"{harness.VIM_BIN} is required")
class ScorerTests(unittest.TestCase):
    def test_exact_edit_passes(self):
        result = score_task(TASK, TASK["reference"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["partial"], 1.0)
        self.assertEqual(result["efficiency"], 1.0)

    def test_near_miss_gets_partial_credit(self):
        result = score_task(TASK, "dd:wq<CR>")
        self.assertFalse(result["passed"])
        self.assertGreater(result["partial"], 0.0)
        self.assertEqual(result["efficiency"], 0.0)

    def test_bad_notation_is_an_error(self):
        result = score_task(TASK, "<Invalid>")
        self.assertFalse(result["passed"])
        self.assertTrue(result["error"].startswith("bad-notation:"))


class SummaryTests(unittest.TestCase):
    def test_empty_summary(self):
        self.assertEqual(summarize([]), {
            "tasks": 0,
            "passed": 0,
            "pass_rate": 0.0,
            "avg_efficiency": 0.0,
            "avg_partial": 0.0,
        })


if __name__ == "__main__":
    unittest.main()
