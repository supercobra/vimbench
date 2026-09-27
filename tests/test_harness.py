import shutil
import unittest

import harness


class NotationTests(unittest.TestCase):
    def test_expands_named_control_and_literal_tokens(self):
        self.assertEqual(
            harness.notation_to_bytes("iA<Tab>B<Space>C<BS><Esc><C-V><CR><NL><<"),
            b"iA\tB C\x08\x1b\x16\r\n<",
        )

    def test_encodes_literal_unicode_as_utf8(self):
        self.assertEqual(harness.notation_to_bytes("café"), "café".encode("utf-8"))
        self.assertEqual(harness.keystroke_count("café"), 5)

    def test_rejects_unknown_or_unescaped_tokens(self):
        for notation in ("<Foo>", "a<b"):
            with self.subTest(notation=notation):
                with self.assertRaises(ValueError):
                    harness.notation_to_bytes(notation)

    def test_tokenize_preserves_atomic_tokens(self):
        self.assertEqual(
            harness.tokenize("i<<x<Esc><C-V>"),
            ["i", "<<", "x", "<Esc>", "<C-V>"],
        )


@unittest.skipUnless(shutil.which(harness.VIM_BIN), f"{harness.VIM_BIN} is required")
class VimHarnessTests(unittest.TestCase):
    def test_replays_edit_in_real_vim(self):
        final, error = harness.run_vim("alpha\nbeta\ngamma\n", "jdd:wq<CR>")
        self.assertIsNone(error)
        self.assertEqual(final, "alpha\ngamma\n")

    def test_bad_notation_does_not_invoke_vim(self):
        final, error = harness.run_vim("unchanged\n", "<Nope>")
        self.assertEqual(final, "unchanged\n")
        self.assertTrue(error.startswith("bad-notation:"))


if __name__ == "__main__":
    unittest.main()
