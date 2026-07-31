"""Configuration loading for the SDT inspection tool.

The tool is single-purpose: it inspects SDT network devices, so
the device-type layer (``device_types.csv``, the 8-column
reference format, per-type paging commands) has been removed.
The 6-column CSV format is now the only supported layout, and
the SDT defaults (driver, paging command, command file) are
hard-coded in :data:`models.DEFAULT_SDT_TYPE`.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable

from .models import DEFAULT_SDT_TYPE, Device, ProjectConfig
from .paths import DEFAULT_COMMANDS_FILE, DEFAULT_DEVICES_FILE


DEFAULT_ENCODINGS = (
    "utf-8-sig",
    "utf-8",
    "gb18030",
    "gbk",
    "gb2312",
    "big5",
)

# Row layout for ``config/devices.csv``.  Six fields, in this
# exact order.  Anything else is rejected with a clear error so
# a typo is visible immediately rather than being silently
# mis-mapped onto another column.
EXPECTED_DEVICE_COLUMNS = (
    "name",
    "ip",
    "username",
    "password",
    "protocol",
    "port",
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


def load_devices(path: Path | None = None) -> tuple[list[Device], list[str]]:
    """Read ``config/devices.csv`` and return parsed ``Device`` objects.

    Only the 6-column SDT layout is accepted:
    ``name, ip, username, password, protocol, port``.  Rows with a
    different column count are rejected with a warning that names
    the expected layout, so a typo (e.g. an extra trailing comma)
    is obvious in the UI instead of being silently mis-mapped.
    """
    path = path or DEFAULT_DEVICES_FILE
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
        if len(row) != len(EXPECTED_DEVICE_COLUMNS):
            warnings.append(
                f"设备配置第 {line_no} 行字段数为 {len(row)}，"
                f"应为 6 列（{','.join(EXPECTED_DEVICE_COLUMNS)}），已跳过"
            )
            continue
        name, host, username, password, protocol_value, port_value = (
            cell.strip() for cell in row
        )
        if not name or not host:
            warnings.append(f"设备配置第 {line_no} 行设备名或地址为空，已跳过")
            continue
        protocol = protocol_value.lower()
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
                username=username,
                password=password,
                port=port,
                protocol=protocol,
                type_id=DEFAULT_SDT_TYPE.type_id,
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
    commands_path: Path | None = None,
) -> ProjectConfig:
    devices, device_warnings = load_devices(devices_path)
    warnings: list[str] = list(device_warnings)

    fallback_path = commands_path or DEFAULT_COMMANDS_FILE
    fallback_commands, command_warnings = load_commands(fallback_path)
    warnings.extend(command_warnings)

    config = ProjectConfig(
        devices=devices,
        device_types={DEFAULT_SDT_TYPE.type_id: DEFAULT_SDT_TYPE},
        devices_file=devices_path or DEFAULT_DEVICES_FILE,
        types_file=None,
        commands_file=fallback_path,
        commands_by_type=(
            {DEFAULT_SDT_TYPE.type_id: fallback_commands}
            if fallback_commands
            else {}
        ),
        warnings=warnings,
    )
    return config
