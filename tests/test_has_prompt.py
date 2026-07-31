"""Tests for ``output.has_prompt`` (P1-C).

The previous heuristic matched any line ending in one of
``> # ] $ %`` which silently misclassified confirmation menus
(``[Y/N]``, ``Press any key to continue [Enter]``) as device
prompts and caused the next command's output to be truncated.
"""
import unittest

from sdt_app.output import has_prompt


class HasPromptTests(unittest.TestCase):
    def test_recognises_typical_prompts(self):
        for line in (
            "Switch>",
            "Switch#",
            "[SW1]",
            "[SW1]>",
            "[SW1]#",
            "Router#",
            "core-01>",
        ):
            self.assertTrue(has_prompt(line), f"expected prompt: {line!r}")

    def test_rejects_confirmation_menus(self):
        # The old behaviour: ``[Y/N]`` ended in ``]`` and was
        # treated as a prompt, truncating the next read.
        for line in (
            "[Y/N]",
            "[Yes/No]",
            "[ENTER]",
            "[Continue?]",
            "Press any key to continue [Enter]",
            "Are you sure? [Y/N]",
        ):
            self.assertFalse(has_prompt(line), f"should not be a prompt: {line!r}")

    def test_rejects_bare_prompt_chars(self):
        # Old heuristic matched a single ``>`` as a prompt.
        for line in (">", "#", "]", "$", "%", "> ", "# "):
            self.assertFalse(has_prompt(line), f"should not be a prompt: {line!r}")

    def test_rejects_menu_with_trailing_arrow(self):
        # ``[Y/N] >`` is tricky: ends in ``>`` but starts with a
        # menu marker.  We err on the side of NOT treating it as a
        # prompt so the next read does not get truncated.
        self.assertFalse(has_prompt("[Y/N] >"))

    def test_recognises_prompt_with_whitespace(self):
        # The prompt is on the last non-empty line; trailing
        # blank lines must not confuse the matcher.
        self.assertTrue(has_prompt("line1\nline2\nSwitch>\n\n"))
        self.assertTrue(has_prompt("Switch> \n  \n"))

    def test_handles_empty_output(self):
        self.assertFalse(has_prompt(""))
        self.assertFalse(has_prompt("\n\n\n"))

    def test_carriage_return_normalised(self):
        # The transport layer feeds ``\\r\\n``-delimited strings.
        # Last line still ends with ``>``.
        self.assertTrue(has_prompt("show version\r\nSwitch#"))

    def test_unbracketed_prompt_with_special_char(self):
        # Some legacy SDT firmware uses ``$`` or ``%`` for
        # unprivileged shell prompts.
        self.assertTrue(has_prompt("user$"))
        self.assertTrue(has_prompt("cli%"))


if __name__ == "__main__":
    unittest.main()
