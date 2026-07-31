"""Tests for ``logging_service.redact_sensitive`` (P0-A).

These verify that known credential-shaped substrings are scrubbed
out of any log payload, and that explicit values handed in via
``extra_values`` (typically the device's own password) are
replaced even when they are not preceded by a key name.
"""
import unittest

from sdt_app.logging_service import REDACT_PLACEHOLDER, redact_sensitive


class RedactSensitiveTests(unittest.TestCase):
    def test_scrubs_key_equals_value(self):
        text = "auth failed: password=hunter2 for user admin"
        out = redact_sensitive(text)
        self.assertNotIn("hunter2", out)
        self.assertIn(REDACT_PLACEHOLDER, out)
        self.assertIn("password=", out)

    def test_scrubs_key_colon_value(self):
        text = "trying password: super-secret"
        out = redact_sensitive(text)
        self.assertNotIn("super-secret", out)
        self.assertIn(REDACT_PLACEHOLDER, out)

    def test_scrubs_quoted_value(self):
        text = "Auth failed for user 'admin' with password 'p@ss w0rd!'"
        out = redact_sensitive(text)
        self.assertNotIn("p@ss w0rd!", out)
        self.assertIn(REDACT_PLACEHOLDER, out)

    def test_scrubs_secret_token_apikey(self):
        for key in ("secret", "token", "api_key", "apiKey", "passwd", "pwd"):
            text = f"got {key}=abc123 extra"
            out = redact_sensitive(text)
            self.assertNotIn("abc123", out, f"failed for key={key!r}")
            self.assertIn(REDACT_PLACEHOLDER, out, f"failed for key={key!r}")

    def test_scrubs_with_password_phrase(self):
        text = "raise BadAuth('authentication failed with password hunter2')"
        out = redact_sensitive(text)
        self.assertNotIn("hunter2", out)

    def test_scrubs_bearer_token(self):
        text = "header: Authorization: Bearer eyJabc.def-ghi"
        out = redact_sensitive(text)
        self.assertNotIn("eyJabc.def-ghi", out)
        self.assertIn("Bearer", out)
        self.assertIn(REDACT_PLACEHOLDER, out)

    def test_passes_through_unrelated_text(self):
        text = "Inspection started for 5 devices at 09:30"
        out = redact_sensitive(text)
        self.assertEqual(out, text)

    def test_scrubs_extra_values_explicit(self):
        # The device password is passed as ``extra_values`` so
        # bare appearances in a traceback are caught.
        text = "Traceback: ... auth failed for device 192.168.1.1 user admin pw realpw123 ..."
        out = redact_sensitive(text, extra_values=("realpw123",))
        self.assertNotIn("realpw123", out)
        self.assertIn(REDACT_PLACEHOLDER, out)

    def test_placeholder_itself_is_not_scrubbed(self):
        # If a log line already contains the placeholder, it must
        # not be redacted a second time.
        text = f"password={REDACT_PLACEHOLDER}"
        out = redact_sensitive(text)
        self.assertEqual(out.count(REDACT_PLACEHOLDER), 1)

    def test_empty_string_passes_through(self):
        self.assertEqual(redact_sensitive(""), "")
        self.assertIsNone(redact_sensitive(None))


if __name__ == "__main__":
    unittest.main()
