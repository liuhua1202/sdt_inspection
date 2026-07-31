import unittest

from sdt_app.output import decode_bytes, filter_output, has_pagination, has_prompt, normalize_output


class OutputTests(unittest.TestCase):
    def test_decodes_gb18030_before_replacing(self):
        value = "设备正常".encode("gb18030")
        self.assertEqual(decode_bytes(value, ("utf-8", "gb18030")), "设备正常")

    def test_detects_common_prompts_and_pagination(self):
        self.assertTrue(has_prompt("output\nSDT>"))
        self.assertTrue(has_prompt("output\nrouter#"))
        self.assertTrue(has_pagination("data\n--More--"))

    def test_filters_echo_pagination_and_repeated_blank_lines(self):
        text = "show run\nvalue\n\n\n--More--\nrouter>\n"
        result = filter_output(text, "show run")
        self.assertIn("value", result)
        self.assertNotIn("show run", result)
        self.assertNotIn("--More--", result)
        self.assertEqual(normalize_output("a\n\n\n"), "a\n")

    def test_filter_output_strips_blanks_between_every_line(self):
        """SDT devices emit a trailing blank line after every
        line of output (``line\\r\\n\\r\\n`` per line).  After our
        CRLF/CR normalisation that becomes ``line\\n\\n`` per line,
        and the file writer used to record
        ``content\\n\\ncontent\\n\\ncontent`` in the per-device log
        -- making a 5-command inspection look 2x as long as it
        really is.  ``filter_output`` should drop those blanks
        so the captured output is one content line per source
        line, exactly as the operator typed it.
        """
        # Simulate the raw channel bytes for ``show node`` on
        # a real SDT device: each line followed by ``\r\n\r\n``.
        raw = "This is branch node\r\n\r\nIt is inactive\r\n\r\n" \
              "Wan link 1 is down\r\n\r\nWan link 2 is down\r\n\r\n" \
              "[SDT-test]#"
        result = filter_output(raw, "show node")
        # The bracketed prompt is kept (we only drop pagination
        # markers and the command echo, not real prompts).
        self.assertNotIn("\n\n", result)
        self.assertIn("This is branch node", result)
        self.assertIn("It is inactive", result)
        self.assertIn("Wan link 1 is down", result)
        self.assertIn("Wan link 2 is down", result)
        # And no internal blank line is preserved.
        for chunk in ("branch node\n\nIt", "inactive\n\nWan", "down\n\nWan"):
            self.assertNotIn(
                chunk, result,
                f"unexpected blank line survived in: {result!r}",
            )

    def test_filter_output_empty_input(self):
        self.assertEqual(filter_output(""), "")
        self.assertEqual(filter_output("\n\n\n"), "")

    def test_filter_output_only_blanks_returns_empty(self):
        # The command echo and pagination filters might strip
        # every content line; the result should be the empty
        # string, not a string of newlines.
        self.assertEqual(filter_output("\r\n\r\n\r\n", "show run"), "")


if __name__ == "__main__":
    unittest.main()
