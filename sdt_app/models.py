"""Core data models used by the SDT inspection application.

The tool is single-purpose (SDT only) so the device-type layer
is collapsed to a single module-level constant,
:data:`DEFAULT_SDT_TYPE`.  ``config_loader`` and
``inspection_service`` both reference that constant directly;
there is no per-operator customisation of driver, paging
command, or command-file path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DeviceType:
    """Connection and command defaults for a device family.

    The dataclass is kept generic so ``DEFAULT_SDT_TYPE`` and
    any future internal profiles share the same shape; runtime
    code does not let the operator override any of these fields.
    """

    type_id: str
    name: str
    ssh_driver: str = "paramiko"
    telnet_driver: str = "generic_termserver_telnet"
    needs_enable: bool = False
    # ``disable_paging_command`` is intentionally a plain string
    # rather than ``Optional``: ``DeviceType`` is ``frozen=True``
    # and an empty string is the documented "paging left enabled"
    # sentinel (almost never what you want).
    disable_paging_command: str = "screen-length 0 temporary"
    default_protocol: str = "telnet"
    commands_file: Optional[Path] = None

    def protocol(self, requested: str = "") -> str:
        value = (requested or self.default_protocol or "telnet").strip().lower()
        return value if value in {"ssh", "telnet"} else self.default_protocol

    def driver(self, protocol: str) -> str:
        return self.ssh_driver if protocol == "ssh" else self.telnet_driver


# Default SDT device profile.  Hard-coded because the program is
# SDT-only; the previous per-operator ``device_types.csv`` has
# been removed along with the 8-column CSV format.  Operators
# who genuinely need a different profile can fork the project.
DEFAULT_SDT_TYPE: DeviceType = DeviceType(
    type_id="sdt",
    name="SDT \u8bbe\u5907",
    ssh_driver="paramiko",
    telnet_driver="generic_termserver_telnet",
    needs_enable=False,
    # The Huawei-style ``screen-length 0 temporary`` is the
    # common SDT paging-disable idiom.  Empty string would mean
    # "leave paging enabled" which is almost always wrong for
    # the commands this tool issues.
    disable_paging_command="screen-length 0 temporary",
    default_protocol="telnet",
    commands_file=None,  # populated by config_loader when known
)


@dataclass
class Device:
    name: str
    host: str
    username: str = ""
    password: str = field(default="", repr=False)
    port: int = 23
    protocol: str = "telnet"
    type_id: str = "sdt"
    selected: bool = True

    def resolved_protocol(self, device_type: DeviceType | None = None) -> str:
        requested = (self.protocol or "").strip().lower()
        if requested in {"ssh", "telnet"}:
            return requested
        return device_type.protocol() if device_type else "telnet"

    def display_type(self, device_types: dict[str, DeviceType]) -> str:
        return device_types.get(self.type_id, DeviceType(self.type_id, self.type_id)).name


class ResultStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CommandResult:
    command: str
    output: str = ""


@dataclass
class InspectionResult:
    device: Device
    status: ResultStatus
    started_at: datetime
    finished_at: datetime
    command_results: list[CommandResult] = field(default_factory=list)
    log_file: Optional[Path] = None
    error: str = ""

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.finished_at - self.started_at).total_seconds())


@dataclass(frozen=True)
class InspectionEvent:
    """Thread-safe event passed from the service layer to the UI."""

    kind: str
    message: str = ""
    device_name: str = ""
    completed: int = 0
    total: int = 0
    result: Optional[InspectionResult] = None


@dataclass
class ProjectConfig:
    devices: list[Device] = field(default_factory=list)
    device_types: dict[str, DeviceType] = field(default_factory=dict)
    commands_by_type: dict[str, list[str]] = field(default_factory=dict)
    devices_file: Optional[Path] = None
    types_file: Optional[Path] = None
    commands_file: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def commands(self) -> list[str]:
        """Return the first configured command set for legacy callers."""
        for commands in self.commands_by_type.values():
            if commands:
                return commands
        return []
