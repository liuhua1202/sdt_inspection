"""Regression tests for the SSH key fallback in transport._execute_ssh.

When a device's SSH server only advertises ``publickey`` as an
auth method, Paramiko raises ``No authentication methods available``
even though the client passed a password.  The fix looks for a
default SSH key in standard locations and retries; if no key is
available the error is rewritten so the operator sees an
actionable message instead of Paramiko's one-liner.
"""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sdt_app import transport


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


if __name__ == "__main__":
    unittest.main()
