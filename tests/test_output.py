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


if __name__ == "__main__":
    unittest.main()
