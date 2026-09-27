import unittest
from difflib import SequenceMatcher

from multiturn import run_multiturn, summarize_multiturn


TASK = {
    "id": "partial-test",
    "tier": 1,
    "instruction": "Delete the second line.",
    "start": "alpha\nbeta\ngamma\n",
    "target": "alpha\ngamma\n",
    "reference": "jdd:wq<CR>",
}


class DoneAgent:
    def __call__(self, obs):
        return {"done": True}


class MultiTurnScoringTests(unittest.TestCase):
    def test_failed_run_records_final_buffer_similarity(self):
        result = run_multiturn(TASK, DoneAgent())
        expected = round(SequenceMatcher(None, TASK["start"], TASK["target"]).ratio(), 3)
        self.assertFalse(result["passed"])
        self.assertEqual(result["partial"], expected)
        self.assertGreater(result["partial"], 0.0)

        summary = summarize_multiturn([result])
        self.assertEqual(summary["avg_partial"], expected)
        self.assertEqual(summary["avg_turns"], 0.0)

    def test_empty_summary_is_well_defined(self):
        summary = summarize_multiturn([])
        self.assertEqual(summary["tasks"], 0)
        self.assertEqual(summary["avg_turns"], 0.0)


if __name__ == "__main__":
    unittest.main()
