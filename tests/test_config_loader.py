import tempfile
import unittest
from pathlib import Path

from sdt_app.config_loader import (
    EXPECTED_DEVICE_COLUMNS,
    load_commands,
    load_devices,
    load_project,
)


class ConfigLoaderTests(unittest.TestCase):
    def test_loads_six_column_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_bytes(
                "# 设备名,IP,用户名,密码,协议,端口\n设备一,10.0.0.1,admin,secret,telnet,23\n".encode("gb18030")
            )
            devices, warnings = load_devices(path)
            self.assertFalse(warnings)
            self.assertEqual(devices[0].type_id, "sdt")
            self.assertEqual(devices[0].port, 23)
            self.assertEqual(devices[0].protocol, "telnet")
            self.assertEqual(devices[0].username, "admin")
            self.assertEqual(devices[0].password, "secret")

    def test_six_column_via_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text(
                "switch1,10.0.0.1,admin,secret,ssh,2222\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(path)
            self.assertFalse(warnings)
            device = devices[0]
            self.assertEqual(device.username, "admin")
            self.assertEqual(device.password, "secret")
            self.assertEqual(device.protocol, "ssh")
            self.assertEqual(device.port, 2222)
            self.assertEqual(device.type_id, "sdt")

    def test_invalid_port_is_reported_and_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text("bad,192.0.2.1,user,pwd,telnet,99999\n", encoding="utf-8")
            devices, warnings = load_devices(path)
            self.assertEqual(devices, [])
            self.assertTrue(warnings)

    def test_seven_column_row_is_rejected(self):
        # The tool only supports the 6-column SDT format.  An
        # accidental extra column (e.g. trailing comma) must be
        # rejected with a clear warning that names the expected
        # layout, not silently misparsed.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text(
                "core,192.0.2.1,admin,pwd,en,2222,ssh\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(path)
            self.assertEqual(devices, [])
            self.assertTrue(warnings)
            self.assertTrue(
                any("\u5b57\u6bb5\u6570" in w for w in warnings),
                f"expected column-count warning, got {warnings!r}",
            )
            self.assertTrue(
                any("6 \u5217" in w for w in warnings),
                f"expected 6-column hint, got {warnings!r}",
            )

    def test_eight_column_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text(
                "core,192.0.2.1,sdt,admin,pwd,en,2222,ssh\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(path)
            self.assertEqual(devices, [])
            self.assertTrue(
                any("6 \u5217" in w for w in warnings),
                f"expected 6-column hint, got {warnings!r}",
            )

    def test_five_column_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text("core,192.0.2.1,admin,pwd,telnet\n", encoding="utf-8")
            devices, warnings = load_devices(path)
            self.assertEqual(devices, [])
            self.assertTrue(warnings)

    def test_blank_name_or_host_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text(
                ",192.0.2.1,admin,pwd,telnet,23\ncore,,admin,pwd,telnet,23\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(path)
            self.assertEqual(devices, [])
            self.assertEqual(len(warnings), 2)

    def test_protocol_must_be_ssh_or_telnet(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text("core,192.0.2.1,admin,pwd,rsh,22\n", encoding="utf-8")
            devices, warnings = load_devices(path)
            self.assertEqual(devices, [])
            self.assertTrue(warnings)

    def test_header_row_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text(
                "name,ip,user,password,protocol,port\n"
                "core,192.0.2.1,admin,pwd,telnet,23\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(path)
            self.assertFalse(warnings)
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0].name, "core")

    def test_missing_file_yields_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            devices, warnings = load_devices(Path(directory) / "missing.csv")
            self.assertEqual(devices, [])
            self.assertTrue(warnings)
            self.assertTrue(any("\u4e0d\u5b58\u5728" in w for w in warnings))

    def test_default_port_applied_when_blank(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text(
                "core,192.0.2.1,admin,pwd,ssh,\ncore2,192.0.2.2,admin,pwd,telnet,\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(path)
            self.assertFalse(warnings, warnings)
            self.assertEqual(devices[0].port, 22)  # ssh default
            self.assertEqual(devices[1].port, 23)  # telnet default

    def test_project_loads_commands(self):
        config = load_project()
        # SDT-only: device_types has exactly one entry.
        self.assertEqual(list(config.device_types), ["sdt"])
        self.assertIn("sdt", config.commands_by_type)
        self.assertTrue(config.commands_by_type["sdt"])

    def test_commands_ignore_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commands.txt"
            path.write_text("# comment\n\nshow version\n  show int  \n", encoding="utf-8")
            commands, warnings = load_commands(path)
            self.assertFalse(warnings)
            self.assertEqual(commands, ["show version", "show int"])

    def test_expected_columns_constant_matches_documented_layout(self):
        # If the layout changes, this test should change too so
        # the docs and the loader stay in lock-step.
        self.assertEqual(
            EXPECTED_DEVICE_COLUMNS,
            ("name", "ip", "username", "password", "protocol", "port"),
        )


if __name__ == "__main__":
    unittest.main()
