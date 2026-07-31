"""Regression tests for the SSH key fallback in transport._execute_ssh.

When a device's SSH server only advertises ``publickey`` as an
auth method, Paramiko raises ``BadAuthenticationType("No
authentication methods available")`` even though the client passed
a password.  The fix looks for a default SSH key in standard
locations and retries; if no key is available the error is
rewritten so the operator sees an actionable message instead of
Paramiko's one-liner.

Three sub-paths are exercised by :class:`ExecuteSshFallbackTests`:

* ``BadAuthenticationType`` + key found  -> retry with ``pkey=``
* ``BadAuthenticationType`` + no key     -> actionable error
* any other auth-related exception       -> no key fallback
"""
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sdt_app import transport
from sdt_app.models import DEFAULT_SDT_TYPE, Device


class _FakeParamiko:
    """Stand-in for the real paramiko module.

    We avoid importing the real one so the test does not pull
    paramiko's 30+ submodules and so the mock can supply exactly
    the exception classes the helper needs.
    """

    class PasswordRequiredException(Exception):
        pass

    class Ed25519Key:
        @staticmethod
        def from_private_key_file(_path):
            raise _FakeParamiko.PasswordRequiredException("needs passphrase")

    class RSAKey:
        @staticmethod
        def from_private_key_file(_path):
            raise OSError("unreadable")

    class ECDSAKey:
        @staticmethod
        def from_private_key_file(_path):
            raise OSError("unreadable")


class CandidateKeyPathsTests(unittest.TestCase):
    def test_includes_home_ssh_keys_first(self):
        paths = [str(p) for p in transport._candidate_ssh_key_paths()]
        # ~/.ssh/id_ed25519 is the operator's most likely current key.
        self.assertTrue(
            any(p.endswith(str(Path.home() / ".ssh" / "id_ed25519")) for p in paths),
            f"expected ~/.ssh/id_ed25519 in {paths!r}",
        )
        ed_idx = next(
            i for i, p in enumerate(paths)
            if p.endswith(str(Path.home() / ".ssh" / "id_ed25519"))
        )
        rsa_idx = next(
            i for i, p in enumerate(paths)
            if p.endswith(str(Path.home() / ".ssh" / "id_rsa"))
        )
        self.assertLess(ed_idx, rsa_idx)

    def test_includes_project_config_keys(self):
        from sdt_app.paths import BASE_DIR
        paths = [str(p) for p in transport._candidate_ssh_key_paths()]
        self.assertTrue(
            any(
                str(BASE_DIR) in p and p.endswith("id_ed25519")
                for p in paths
            ),
            f"expected BASE_DIR/config/id_ed25519 in {paths!r}",
        )
        self.assertTrue(
            any(
                str(BASE_DIR) in p and p.endswith("id_rsa")
                for p in paths
            ),
            f"expected BASE_DIR/config/id_rsa in {paths!r}",
        )


class TryLoadKeyTests(unittest.TestCase):
    def _fake_path(self):
        p = MagicMock(spec=Path)
        p.is_file.return_value = True
        p.__str__.return_value = "/fake/key"
        return p

    def test_returns_none_when_no_candidates(self):
        with patch.object(transport, "_candidate_ssh_key_paths", return_value=[]):
            self.assertIsNone(
                transport._try_load_default_ssh_key(_FakeParamiko),
            )

    def test_skips_files_with_no_path(self):
        # A candidate that is not a file is silently skipped.
        p = MagicMock(spec=Path)
        p.is_file.return_value = False
        with patch.object(
            transport, "_candidate_ssh_key_paths", return_value=[p]
        ):
            self.assertIsNone(transport._try_load_default_ssh_key(_FakeParamiko))

    def test_returns_key_when_loader_succeeds(self):
        # The Ed25519 loader in _FakeParamiko raises
        # ``PasswordRequiredException`` for any file, but a
        # *real* unencrypted key would not raise that.  Replace
        # Ed25519Key with one that reports "wrong format" so the
        # helper moves on to RSAKey, which is rigged to succeed.
        sentinel = "ok_key"

        class _WrongFormatEd25519:
            @staticmethod
            def from_private_key_file(_path):
                raise ValueError("not an Ed25519 key")

        class _GoodRSA:
            @staticmethod
            def from_private_key_file(_path):
                return sentinel

        class _GoodParamiko(_FakeParamiko):
            Ed25519Key = _WrongFormatEd25519
            RSAKey = _GoodRSA

        p = self._fake_path()
        with patch.object(
            transport, "_candidate_ssh_key_paths", return_value=[p]
        ):
            self.assertEqual(
                transport._try_load_default_ssh_key(_GoodParamiko),
                sentinel,
            )

    def test_encrypted_key_is_skipped_returns_none(self):
        # _FakeParamiko's Ed25519Key raises PasswordRequiredException.
        # All other loaders raise OSError.  No key is returned.
        p = self._fake_path()
        with patch.object(
            transport, "_candidate_ssh_key_paths", return_value=[p]
        ):
            self.assertIsNone(transport._try_load_default_ssh_key(_FakeParamiko))


def _build_paramiko_with_bad_auth(connect_log, fail_count=1, channel_prompt=b"prompt# "):
    """Return a fake ``paramiko`` module stand-in.

    The first ``fail_count`` calls to ``SSHClient.connect`` raise
    ``BadAuthenticationType("No authentication methods available")``;
    subsequent calls succeed.  ``connect_log`` is appended with
    the kwargs of every call so the test can assert what was
    offered to the second attempt.
    """

    class _BadAuthType(Exception):
        def __init__(self, explanation, allowed_types=None, types_tried=None):
            super().__init__(explanation)
            self.allowed_types = allowed_types or ["publickey"]
            self.types_tried = types_tried or ["password"]

    class _Channel:
        def __init__(self):
            self.sent = []
            self.timeout = None
            self.closed = False

        def settimeout(self, t):
            self.timeout = t

        def send(self, data):
            self.sent.append(data)

        def recv(self, _n):
            return channel_prompt

        def recv_ready(self):
            return True

        def close(self):
            self.closed = True

    class _Client:
        def __init__(self):
            self.host_keys_loaded = False
            self.policy = None
            self.channel = _Channel()

        def load_system_host_keys(self):
            self.host_keys_loaded = True

        def set_missing_host_key_policy(self, policy):
            self.policy = policy

        def connect(self, **kwargs):
            connect_log.append(kwargs)
            if len(connect_log) <= fail_count:
                raise _BadAuthType(
                    "No authentication methods available",
                    allowed_types=["publickey"],
                    types_tried=["password"],
                )

        def invoke_shell(self):
            return self.channel

        def close(self):
            pass

    class _FakeParamiko:
        BadAuthenticationType = _BadAuthType
        PasswordRequiredException = type(
            "PasswordRequiredException", (Exception,), {}
        )
        AutoAddPolicy = MagicMock
        SSHClient = _Client

    return _FakeParamiko


class ExecuteSshFallbackTests(unittest.TestCase):
    """Integration-style tests for the ``BadAuthenticationType``
    branch in ``transport._execute_ssh``.  These mock just enough
    of paramiko to drive the connect path without actually
    touching the network; the post-connect read loop is allowed
    to fail in a controlled way (it raises ``TransportError``)
    because we only care about the catch+retry logic here.
    """

    def _make_device(self):
        return Device(
            name="x",
            host="1.2.3.4",
            username="u",
            password="p",
            protocol="ssh",
            port=22,
        )

    def test_bad_auth_type_triggers_key_retry(self):
        connect_log = []
        fake_paramiko = _build_paramiko_with_bad_auth(connect_log, fail_count=1)
        device = self._make_device()
        stop = threading.Event()
        # Tight timeouts so the post-connect read loop bails out
        # quickly when the mock channel does not produce a real
        # SDT prompt; we only need the retry to be exercised.
        options = transport.TransportOptions(
            read_timeout=0.3, recv_timeout=0.05, quiet_timeout=0.05,
        )
        sentinel_key = "found_key"

        with patch.object(
            transport, "_ensure_paramiko", return_value=fake_paramiko
        ), patch.object(
            transport, "_try_load_default_ssh_key", return_value=sentinel_key
        ):
            try:
                transport._execute_ssh(
                    device, DEFAULT_SDT_TYPE, [], options, stop,
                    log_warning=None, connection_tracker=None,
                )
            except transport.TransportError:
                # Post-connect read loop failure is fine; we only
                # care that the key retry happened.
                pass

        self.assertEqual(len(connect_log), 2)
        # First attempt offered the password.
        self.assertEqual(connect_log[0].get("password"), "p")
        self.assertNotIn("pkey", connect_log[0])
        # Second attempt dropped the password and attached the key.
        self.assertNotIn("password", connect_log[1])
        self.assertIs(connect_log[1].get("pkey"), sentinel_key)

    def test_bad_auth_type_without_key_raises_actionable_error(self):
        connect_log = []
        fake_paramiko = _build_paramiko_with_bad_auth(connect_log, fail_count=999)
        device = self._make_device()
        stop = threading.Event()
        options = transport.TransportOptions(connect_timeout=1.0)

        with patch.object(
            transport, "_ensure_paramiko", return_value=fake_paramiko
        ), patch.object(
            transport, "_try_load_default_ssh_key", return_value=None
        ):
            with self.assertRaises(transport.TransportError) as cm:
                transport._execute_ssh(
                    device, DEFAULT_SDT_TYPE, [], options, stop,
                    log_warning=None, connection_tracker=None,
                )

        msg = str(cm.exception)
        self.assertIn("id_ed25519", msg)
        self.assertIn("id_rsa", msg)
        self.assertIn("ssh-keygen -p", msg)
        # The error must chain back to the *original* trigger
        # (BadAuthenticationType) so the traceback shows the
        # real reason the fallback path was taken.
        self.assertIsNotNone(cm.exception.__cause__)
        # No retry: only one connect attempt.
        self.assertEqual(len(connect_log), 1)

    def test_other_auth_exception_does_not_trigger_fallback(self):
        """``AuthenticationException`` (or any non-BadAuthenticationType
        failure) must NOT trigger the key fallback.  Only the
        structured "server rejected everything we offered" case
        does."""

        class _AuthException(Exception):
            pass

        connect_log = []

        class _Client:
            def load_system_host_keys(self):
                pass

            def set_missing_host_key_policy(self, _policy):
                pass

            def connect(self, **kwargs):
                connect_log.append(kwargs)
                raise _AuthException("Auth failed")

            def invoke_shell(self):
                raise AssertionError("invoke_shell should not be reached")

            def close(self):
                pass

        class _FakeParamiko:
            # Distinct class hierarchy from _AuthException so the
            # specific ``except paramiko.BadAuthenticationType``
            # branch in _execute_ssh does NOT match.
            BadAuthenticationType = type("BadAuthenticationType", (Exception,), {})
            AuthenticationException = _AuthException
            PasswordRequiredException = type(
                "PasswordRequiredException", (Exception,), {}
            )
            AutoAddPolicy = MagicMock
            SSHClient = _Client

        device = self._make_device()
        stop = threading.Event()
        options = transport.TransportOptions(connect_timeout=1.0)

        with patch.object(
            transport, "_ensure_paramiko", return_value=_FakeParamiko
        ) as loader:
            with self.assertRaises(transport.TransportError):
                transport._execute_ssh(
                    device, DEFAULT_SDT_TYPE, [], options, stop,
                    log_warning=None, connection_tracker=None,
                )

        # Key loader was NEVER consulted -- the catch is type-based.
        self.assertEqual(len(connect_log), 1)


if __name__ == "__main__":
    unittest.main()
