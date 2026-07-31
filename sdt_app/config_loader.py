"""Configuration loading with compatibility for the original SDT CSV format."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable

from .models import Device, DeviceType, ProjectConfig
from .paths import (
    DEFAULT_COMMANDS_FILE,
    DEFAULT_DEVICES_FILE,
    DEFAULT_TYPES_FILE,
)


DEFAULT_ENCODINGS = (
    "utf-8-sig",
    "utf-8",
    "gb18030",
    "gbk",
    "gb2312",
    "big5",
)


class ConfigError(ValueError):
    """Raised when a configuration cannot be interpreted safely."""


def _read_text(path: Path, encodings: Iterable[str] = DEFAULT_ENCODINGS) -> tuple[str, str]:
    raw = path.read_bytes()
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ConfigError(f"无法识别文件编码: {path} ({last_error})")


def _rows(text: str, delimiter: str = ",") -> list[list[str]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    result: list[list[str]] = []
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        if row[0].lstrip().startswith("#"):
            continue
        result.append([cell.strip() for cell in row])
    return result


def _read_rows(path: Path) -> tuple[list[list[str]], str]:
    text, encoding = _read_text(path)
    delimiter = "|" if path.suffix.lower() == ".txt" else ","
    if delimiter == "," and "|" in text and "," not in text.splitlines()[0]:
        delimiter = "|"
    return _rows(text, delimiter), encoding


def _is_header(row: list[str], keywords: tuple[str, ...]) -> bool:
    cells = {cell.strip().lower() for cell in row}
    return any(keyword.lower() in cells for keyword in keywords)


def default_device_type() -> DeviceType:
    return DeviceType(
        type_id="sdt",
        name="SDT设备",
        ssh_driver="paramiko",
        telnet_driver="generic_termserver_telnet",
        default_protocol="telnet",
        commands_file=DEFAULT_COMMANDS_FILE,
    )


def load_device_types(path: Path | None = None) -> tuple[dict[str, DeviceType], list[str]]:
    path = path or DEFAULT_TYPES_FILE
    warnings: list[str] = []
    types: dict[str, DeviceType] = {"sdt": default_device_type()}
    if not path.exists():
        return types, warnings

    try:
        rows, _ = _read_rows(path)
    except (OSError, ConfigError) as exc:
        return types, [f"设备类型配置加载失败: {exc}"]

    for line_no, row in enumerate(rows, 1):
        if _is_header(row, ("type_id", "name", "\u7c7b\u578bID", "\u540d\u79f0")):
            continue
        if len(row) < 8:
            warnings.append(f"设备类型配置第 {line_no} 行字段不足，已跳过")
            continue
        type_id, name, ssh_driver, telnet_driver = (value.strip() for value in row[:4])
        try:
            needs_enable = row[4].strip().lower() in {"1", "true", "yes", "是"}
            protocol = row[6].strip().lower() or "ssh"
            if protocol not in {"ssh", "telnet"}:
                raise ConfigError(f"协议必须是 ssh 或 telnet: {protocol}")
            command_value = row[7].strip()
            command_path = Path(command_value)
            if not command_path.is_absolute():
                command_path = path.parent / command_path
            disable_paging = row[5].strip()
            if not disable_paging:
                # Empty paging command means a long output (e.g.
                # ``show running-config``) will be paginated and
                # truncated.  The SDT default already provides
                # ``screen-length 0 temporary`` so we only warn
                # for the operator-configured types.
                warnings.append(
                    f"设备类型 {type_id!r} 未配置禁用分页命令，长输出可能被截断"
                )
            types[type_id] = DeviceType(
                type_id=type_id,
                name=name or type_id,
                ssh_driver=ssh_driver or "paramiko",
                telnet_driver=telnet_driver or "generic_termserver_telnet",
                needs_enable=needs_enable,
                disable_paging_command=disable_paging,
                default_protocol=protocol,
                commands_file=command_path,
            )
        except (IndexError, ConfigError) as exc:
            warnings.append(f"设备类型配置第 {line_no} 行无效: {exc}")
    return types, warnings


def _parse_port(value: str, default: int, line_no: int, warnings: list[str]) -> int:
    value = value.strip()
    if not value:
        return default
    try:
        port = int(value)
    except ValueError:
        warnings.append(f"设备配置第 {line_no} 行端口不是整数，已跳过")
        raise ConfigError("invalid port")
    if not 1 <= port <= 65535:
        warnings.append(f"设备配置第 {line_no} 行端口超出范围，已跳过")
        raise ConfigError("port out of range")
    return port


def load_devices(
    path: Path | None = None,
    device_types: dict[str, DeviceType] | None = None,
) -> tuple[list[Device], list[str]]:
    path = path or DEFAULT_DEVICES_FILE
    device_types = device_types or {"sdt": default_device_type()}
    warnings: list[str] = []
    if not path.exists():
        return [], [f"设备列表文件不存在: {path}"]

    try:
        rows, _ = _read_rows(path)
    except (OSError, ConfigError) as exc:
        return [], [f"设备列表加载失败: {exc}"]

    devices: list[Device] = []
    for line_no, row in enumerate(rows, 1):
        if _is_header(row, ("device", "ip", "name", "host", "\u8bbe\u5907\u540d", "\u8bbe\u5907\u540d\u79f0")):
            continue
        if len(row) < 4:
            warnings.append(f"设备配置第 {line_no} 行至少需要设备名、地址、用户名、密码，已跳过")
            continue

        # 兼容参考项目的 8 列格式：名称,地址,类型ID,用户,密码,enable密码,端口,协议
        # 也兼容本项目原有 6 列格式：名称,地址,用户,密码,协议,端口。
        # 8-column (reference) format has the device type id in
        # column 2; the 6-column (legacy SDT) format has the username
        # there.  Any row with 7+ columns is treated as the reference
        # format (with ``sdt`` as the fallback type id) so we never
        # silently drop the enable_password / port / protocol columns
        # the operator typed.  6 columns stays strictly legacy.
        if len(row) >= 7:
            reference_format = True
            name, host, type_id = row[:3]
            username = row[3] if len(row) > 3 else ""
            password = row[4] if len(row) > 4 else ""
            enable_password = row[5] if len(row) > 5 else ""
            port_value = row[6] if len(row) > 6 else ""
            protocol_value = row[7] if len(row) > 7 else ""
            # If a 7-column row's type id does not match a known
            # device, the operator almost certainly wanted the
            # 8-column reference format but is missing the protocol
            # column at the end.  Surface that so the next person to
            # edit the file knows the format choice was made for them.
            if len(row) == 7 and type_id not in device_types:
                warnings.append(
                    f"设备配置第 {line_no} 行按 8 列格式解析（type_id 未知，默认 SDT）；"
                    f"如确为 6 列+enable 旧格式，请改用 8 列并显式写 type_id"
                )
        else:
            reference_format = False
            name, host = row[:2]
            type_id = "sdt"
            username = row[2] if len(row) > 2 else ""
            password = row[3] if len(row) > 3 else ""
            enable_password = ""
            protocol_value = row[4] if len(row) > 4 else ""
            port_value = row[5] if len(row) > 5 else ""

        name, host, type_id = name.strip(), host.strip(), type_id.strip() or "sdt"
        if not name or not host:
            warnings.append(f"设备配置第 {line_no} 行设备名或地址为空，已跳过")
            continue
        device_type = device_types.get(type_id)
        if device_type is None:
            warnings.append(f"设备配置第 {line_no} 行引用了未知设备类型 {type_id}，使用 SDT 默认类型")
            device_type = device_types.get("sdt", default_device_type())
            type_id = device_type.type_id

        protocol = (protocol_value or device_type.default_protocol).strip().lower()
        if protocol not in {"ssh", "telnet"}:
            warnings.append(f"设备配置第 {line_no} 行协议无效，已跳过")
            continue
        default_port = 22 if protocol == "ssh" else 23
        try:
            port = _parse_port(port_value, default_port, line_no, warnings)
        except ConfigError:
            continue
        devices.append(
            Device(
                name=name,
                host=host,
                username=username.strip(),
                password=password.strip(),
                enable_password=enable_password.strip(),
                port=port,
                protocol=protocol,
                type_id=type_id,
            )
        )
    return devices, warnings


def load_commands(path: Path) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if not path.exists():
        return [], [f"命令文件不存在: {path}"]
    try:
        text, _ = _read_text(path)
    except (OSError, ConfigError) as exc:
        return [], [f"命令文件加载失败: {exc}"]
    commands = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not commands:
        warnings.append(f"命令文件没有有效命令: {path}")
    return commands, warnings


def load_project(
    devices_path: Path | None = None,
    types_path: Path | None = None,
    commands_path: Path | None = None,
) -> ProjectConfig:
    types, warnings = load_device_types(types_path)
    devices, device_warnings = load_devices(devices_path, types)
    warnings.extend(device_warnings)
    config = ProjectConfig(
        devices=devices,
        device_types=types,
        devices_file=devices_path or DEFAULT_DEVICES_FILE,
        types_file=types_path or (DEFAULT_TYPES_FILE if DEFAULT_TYPES_FILE.exists() else None),
    )

    fallback_path = commands_path or DEFAULT_COMMANDS_FILE
    config.commands_file = fallback_path
    fallback_commands, command_warnings = load_commands(fallback_path)
    warnings.extend(command_warnings)

    if commands_path is not None:
        for type_id in types:
            if fallback_commands:
                config.commands_by_type[type_id] = fallback_commands
    else:
        for type_id, device_type in types.items():
            command_file = device_type.commands_file
            if command_file and command_file.exists():
                commands, file_warnings = load_commands(command_file)
                warnings.extend(file_warnings)
            else:
                commands = fallback_commands
            if commands:
                config.commands_by_type[type_id] = commands

    if not config.commands_by_type and fallback_commands:
        config.commands_by_type["sdt"] = fallback_commands
    config.warnings = warnings
    return config
