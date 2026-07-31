"""Regression tests for the ``Device.enable_password`` removal.

When the program was simplified to be SDT-only, the
``Device.enable_password`` field was dropped.  A stale reference
in ``inspection_service._run_device`` (``device_secrets =
(device.password, device.enable_password)``) survived the refactor
and raised ``AttributeError`` on every inspection, which the broad
``except Exception`` in the service turned into a per-device
FAILED status.  The user saw "no execution, immediate failure".

These tests pin the contract: the field is gone, the
inspection service does not touch it, and the transport layer
does not either.
"""
import ast
import unittest
from pathlib import Path

from sdt_app import inspection_service, transport
from sdt_app.models import Device


class DeviceShapeTests(unittest.TestCase):
    def test_device_does_not_have_enable_password(self):
        # The field is gone, so attribute access must raise.
        d = Device(name="core", host="10.0.0.1")
        with self.assertRaises(AttributeError):
            _ = d.enable_password

    def test_device_repr_does_not_leak_password(self):
        d = Device(
            name="core",
            host="10.0.0.1",
            username="admin",
            password="realpw123",
        )
        text = repr(d)
        self.assertNotIn("realpw123", text)
        self.assertIn("admin", text)


class ServiceWiringTests(unittest.TestCase):
    def test_run_device_does_not_touch_enable_password(self):
        # Static check: the source of ``_run_device`` must not
        # reference the dropped field.  We parse the file and
        # walk the AST so a typo somewhere in the function body
        # (e.g. a half-rewritten line) still gets caught.
        src = Path(inspection_service.__file__).read_text(
            encoding="utf-8"
        )
        tree = ast.parse(src)
        offenders: list[tuple[str, int]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_run_device":
                continue
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "device"
                    and sub.attr == "enable_password"
                ):
                    offenders.append((node.name, sub.lineno))
        self.assertEqual(
            offenders,
            [],
            "_run_device still references device.enable_password: "
            f"{offenders!r}",
        )

    def test_transport_does_not_touch_device_enable_password(self):
        # Same check for the transport module -- both the netmiko
        # and the Paramiko paths had stale enable blocks.
        src = Path(transport.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        offenders: list[tuple[str, int]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "device"
                and node.attr == "enable_password"
            ):
                offenders.append((node.lineno,))
        self.assertEqual(
            offenders,
            [],
            "transport still references device.enable_password: "
            f"{offenders!r}",
        )


if __name__ == "__main__":
    unittest.main()
