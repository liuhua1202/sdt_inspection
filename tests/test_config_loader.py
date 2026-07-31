import tempfile
import unittest
from pathlib import Path

from sdt_app.config_loader import load_devices, load_device_types, load_project, load_commands


class ConfigLoaderTests(unittest.TestCase):
    def test_loads_original_sdt_six_column_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_bytes(
                "# 设备名,IP,用户名,密码,协议,端口\n设备一,10.0.0.1,admin,secret,telnet,23\n".encode("gb18030")
            )
            types, warnings = load_device_types(Path(directory) / "missing.csv")
            devices, device_warnings = load_devices(path, types)
            self.assertFalse(warnings)
            self.assertFalse(device_warnings)
            self.assertEqual(devices[0].type_id, "sdt")
            self.assertEqual(devices[0].port, 23)
            self.assertEqual(devices[0].protocol, "telnet")

    def test_loads_reference_eight_column_format(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            types_file = directory / "device_types.csv"
            types_file.write_text(
                "id,name,ssh,telnet,enable,paging,protocol,commands\n"
                "1,Cisco,cisco_ios,cisco_ios_telnet,1,terminal length 0,ssh,commands.txt\n",
                encoding="utf-8",
            )
            types, warnings = load_device_types(types_file)
            self.assertFalse(warnings)
            devices_file = directory / "devices.csv"
            devices_file.write_text(
                "name,host,type,user,password,enable,port,protocol\n"
                "core,192.0.2.1,1,admin,pwd,en,22,ssh\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(devices_file, types)
            self.assertFalse(warnings)
            self.assertEqual(devices[0].type_id, "1")
            self.assertEqual(devices[0].enable_password, "en")
            self.assertEqual(devices[0].protocol, "ssh")

    def test_invalid_port_is_reported_and_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text("bad,192.0.2.1,user,pwd,telnet,99999\n", encoding="utf-8")
            devices, warnings = load_devices(path)
            self.assertEqual(devices, [])
            self.assertTrue(warnings)

    def test_project_loads_per_type_commands(self):
        config = load_project()
        self.assertIn("sdt", config.device_types)
        self.assertTrue(config.devices)
        self.assertTrue(config.commands_by_type["sdt"])

    def test_commands_ignore_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commands.txt"
            path.write_text("# comment\n\nshow version\n  show int  \n", encoding="utf-8")
            commands, warnings = load_commands(path)
            self.assertFalse(warnings)
            self.assertEqual(commands, ["show version", "show int"])

    # ------------------------------------------------------------------
    # P0-B regression: 7-column rows must not silently drop the
    # enable_password / port / protocol columns.  The previous
    # heuristic misclassified a 7-column row with an unknown
    # ``row[2]`` as legacy 6-column, which discarded the 7th column
    # and replaced the enable_password with a protocol value.
    # ------------------------------------------------------------------
    def test_seven_column_with_known_type_uses_reference_format(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            types_file = directory / "device_types.csv"
            types_file.write_text(
                "id,name,ssh,telnet,enable,paging,protocol,commands\n"
                "sdt,SDT,paramiko,generic_termserver_telnet,1,,telnet,commands.txt\n",
                encoding="utf-8",
            )
            types, _ = load_device_types(types_file)
            devices_file = directory / "devices.csv"
            # 7 columns: name, host, type_id, user, password, enable, port
            # (no protocol column).
            devices_file.write_text(
                "core,192.0.2.1,sdt,admin,pwd,en,2222\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(devices_file, types)
            self.assertEqual(len(devices), 1, warnings)
            device = devices[0]
            self.assertEqual(device.type_id, "sdt")
            self.assertEqual(device.username, "admin")
            self.assertEqual(device.password, "pwd")
            self.assertEqual(device.enable_password, "en")
            self.assertEqual(device.port, 2222)
            # Protocol column is missing so the device-type default
            # applies; this must be the SDT default (telnet).
            self.assertEqual(device.protocol, "telnet")

    def test_seven_column_with_unknown_type_falls_back_to_sdt(self):
        # The previous bug: a 7-column row whose column 2 was not
        # a known type id used to be parsed as legacy 6-column,
        # dropping the 7th column.  We now always treat >= 7
        # columns as reference format with a fallback type id,
        # so the row is preserved and a warning tells the operator
        # to switch to 8 columns if that was unintentional.
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            types, _ = load_device_types(directory / "missing.csv")
            devices_file = directory / "devices.csv"
            # Reference 8-col layout but with an unknown type id in
            # column 2 and missing protocol.  Should still parse
            # cleanly with type_id defaulting to "sdt".
            devices_file.write_text(
                "core,192.0.2.1,cisco,admin,pwd,en,2222\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(devices_file, types)
            self.assertEqual(len(devices), 1, warnings)
            device = devices[0]
            self.assertTrue(
                any("8 \u5217" in w for w in warnings),
                f"expected 8-col fallback warning, got {warnings!r}",
            )
            self.assertEqual(device.type_id, "sdt")
            self.assertEqual(device.username, "admin")
            self.assertEqual(device.password, "pwd")
            self.assertEqual(device.enable_password, "en")
            self.assertEqual(device.port, 2222)

    def test_six_column_legacy_still_works(self):
        # Sanity check: 6-column legacy rows still parse correctly.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            path.write_text(
                "switch1,10.0.0.1,admin,secret,ssh,2222\n",
                encoding="utf-8",
            )
            devices, warnings = load_devices(path)
            self.assertFalse(warnings)
            self.assertEqual(len(devices), 1)
            device = devices[0]
            self.assertEqual(device.username, "admin")
            self.assertEqual(device.password, "secret")
            self.assertEqual(device.protocol, "ssh")
            self.assertEqual(device.port, 2222)
            self.assertEqual(device.enable_password, "")

    # ------------------------------------------------------------------
    # P1-D: a device type without a disable_paging_command must
    # trigger a warning so the operator notices before the long
    # command output is silently truncated.
    # ------------------------------------------------------------------
    def test_missing_paging_command_emits_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            types_file = directory / "device_types.csv"
            types_file.write_text(
                "id,name,ssh,telnet,enable,paging,protocol,commands\n"
                "no_paging,NoPagingDevice,paramiko,generic_termserver_telnet,0,,ssh,commands.txt\n",
                encoding="utf-8",
            )
            _, warnings = load_device_types(types_file)
            self.assertTrue(
                any("no_paging" in w and "\u5206\u9875" in w for w in warnings),
                f"expected paging warning, got {warnings!r}",
            )

    def test_paging_command_present_does_not_warn(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            types_file = directory / "device_types.csv"
            types_file.write_text(
                "id,name,ssh,telnet,enable,paging,protocol,commands\n"
                "with_paging,WithPaging,paramiko,generic_termserver_telnet,0,screen-length 0,ssh,commands.txt\n",
                encoding="utf-8",
            )
            _, warnings = load_device_types(types_file)
            self.assertFalse(
                any("\u5206\u9875" in w for w in warnings),
                f"unexpected paging warning: {warnings!r}",
            )


if __name__ == "__main__":
    unittest.main()
