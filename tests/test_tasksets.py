import json
import tempfile
import unittest
from pathlib import Path

from tasksets import load_tasks
from tasks import TASKS


class TaskSetTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.synth_path = Path(self.temp_dir.name) / "custom.json"
        self.synthetic = [{
            "id": "syn-test-001",
            "tier": 1,
            "instruction": "Test",
            "start": "a\n",
            "target": "b\n",
            "reference": "cb<Esc>",
        }]
        self.synth_path.write_text(json.dumps(self.synthetic), encoding="utf-8")

    def test_seed_set_does_not_require_synth_file(self):
        self.assertEqual(load_tasks("seed", self.synth_path.with_name("missing.json")), TASKS)

    def test_synth_set_contains_only_synthesized_tasks(self):
        self.assertEqual(load_tasks("synth", self.synth_path), self.synthetic)

    def test_all_combines_seed_and_synthesized_tasks(self):
        tasks = load_tasks("all", self.synth_path)
        self.assertEqual(tasks[:len(TASKS)], TASKS)
        self.assertEqual(tasks[len(TASKS):], self.synthetic)

    def test_unknown_set_is_rejected(self):
        with self.assertRaises(ValueError):
            load_tasks("other", self.synth_path)


if __name__ == "__main__":
    unittest.main()
