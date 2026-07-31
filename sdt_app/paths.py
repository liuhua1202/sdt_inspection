"""Application paths and safe file-name helpers."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


_PACKAGE_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    # PyInstaller: read-only embedded data (icons, templates) is
    # extracted to sys._MEIPASS at startup.  Writable user data
    # (config, logs) lives next to the .exe so the operator can
    # back it up, edit it, and find it without digging in a temp
    # directory.
    DATA_DIR = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    DATA_DIR = _PACKAGE_DIR.parent
    BASE_DIR = _PACKAGE_DIR.parent

# Config is read from / written to the same directory (next to the
# .exe in production, project root in dev).  ensure_directories() will
# seed a template on first launch.
CONFIG_DIR = BASE_DIR / "config"
COMMANDS_DIR = CONFIG_DIR / "commands"
LOG_DIR = BASE_DIR / "InspectionLogs"
LOG_FILE_DIR = LOG_DIR / "logs"
DEFAULT_DEVICES_FILE = CONFIG_DIR / "devices.csv"
DEFAULT_TYPES_FILE = CONFIG_DIR / "device_types.csv"
DEFAULT_COMMANDS_FILE = COMMANDS_DIR / "commands_sdt.txt"


def _seed_config_template(target):
    """Write a minimal config tree at ``target``.

    Used on the first launch of a frozen build to seed
    ``<exe-dir>/config/`` with starter content so the operator has
    somewhere to drop their devices.csv without manually creating
    the directory layout.
    """
    target.mkdir(parents=True, exist_ok=True)
    commands_dir = target / "commands"
    commands_dir.mkdir(exist_ok=True)

    # Example devices.csv (legacy six-column format).
    devices = target / "devices.csv"
    if not devices.exists():
        devices.write_text("""\
Sample device list.  Replace with your own devices.

Format: name, ip, username, password, protocol, port
  (6-column legacy SDT format)
  OR
  name, ip, type_id, username, password, enable_password, port, protocol
  (8-column reference format)

SDT-Device-01,192.168.1.101,admin,password123,telnet,23
SDT-Device-02,192.168.1.102,admin,password124,ssh,22
SDT-Device-03,192.168.1.103,admin,password125,telnet,10023
SDT-Device-04,192.168.1.104,admin,password126,ssh,10022
""", encoding="utf-8")

    # Example command file.
    cmds = commands_dir / "commands_sdt.txt"
    if not cmds.exists():
        cmds.write_text("""\
display version
show running-config
""", encoding="utf-8")

    # README pointing the operator at the docs.
    readme = target / "README.txt"
    if not readme.exists():
        # The leading backslash-newline strips the first newline so the
        # README text starts on the same line as the opening triple-quote.
        readme.write_text("""\
SDT 网络设备巡检 - Windows 端使用说明
============================================================

本文件为 SDT 网络设备巡检程序的 Windows 端使用说明。
首次启动时由 sdt_app/paths._seed_config_template 自动创建，后续可随时修改。

快速上手（5 分钟）
------------------------------------------------------------
1. 打开 config/devices.csv，用你的设备信息替换示例。
   其中两种格式：
   • 6 列形式（与原版 SDT 兼容）：
         name, ip, username, password, protocol, port
       示例: Switch-01,192.168.1.1,admin,password123,ssh,22
   • 8 列形式（带设备类型 id）：
         name, ip, type_id, username, password, enable_password, port, protocol
       示例: Switch-01,192.168.1.1,sdt,admin,password123,,22,ssh
2. 如果你有自己的命令文件，放到 config/commands/ 文件夹下，
   默认加载 config/commands/commands_sdt.txt（含 2 条示例命令）。
3. 双击工作目录下的 sdt_inspection.exe，启动程序。
4. 在主界面勾选要巡检的设备 -> 点“开始巡检” -> 查看日志面板。

常用调节项
------------------------------------------------------------
· 工具栏（顶部）：
  - 并发数：1 - 50（默认 5）
  - 输出编码：自动检测 / UTF-8 / GBK / GB18030 / GB2312 / Big5
  - 严格主机密钥校验：默认关闭（兼容旧 SDT），勾选后只连接已信任的设备
· 定时巡检条（下方）：
  - 打开开关 -> 选择每天 / 每周 / 每月 + 时间 -> 自动定时巡检
  - “下次巡检时间”会面右会显示下一次执行点

输出文件在哪里
------------------------------------------------------------
· 运行日志：InspectionLogs/<YYYY_MM_DD>/<device>_<host>_<timestamp>.txt
  每天一个文件夹，不覆盖。
· 设备状态：在主界面中实时显示（勾选 -> 轮询 + 状态卡）
· 状态卡颜色：
  - 蓝色 = 等待 / 连接中
  - 绿色 = 巡检成功
  - 红色 = 巡检失败
  - 灰色 = 被取消

常见问题
------------------------------------------------------------
Q: 启动时报“encodings module”错误？
A: 高版本 Python 打包 PyInstaller 的问题。本程序使用 onedir 模式已绕性避开。

Q: 连不上设备？
A: 检查：
  1) IP 是否正确 / 能 ping 通
  2) 端口是否开放（SSH=22, Telnet=23）
  3) 用户名 / 密码 是否正确
  4) 设备是否允许该账号登陆
  5) 工具栏 · 严格主机密钥 是否打开

Q: 任务卡总是 0，上面什么都没动静？
A: 可能是设备难以连接或完全未勾选。
  检查：工具栏·并发数不要超过设备总数；
  加选几台设备试试。

Q: 如何重置为初始状态？
A: 删除工作目录下的 config/ 文件夹，重启即可重生示例。

项目资源
------------------------------------------------------------
· 项目仓库：README.md / DESIGN.md / CHANGELOG.md
· 重新打包：python -m PyInstaller sdt_inspection.spec
· 生成多分辨率 favicon：python tools/regen_favicon.py""", encoding="utf-8")


def ensure_directories():
    """Ensure the runtime tree exists.

    Logs always live next to the .exe (writable).  Config is seeded
    on first launch of a frozen build; in dev mode the operator is
    expected to have a config/ tree already checked into the project.
    """
    LOG_FILE_DIR.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):
        # Frozen: seed a template next to the .exe if missing.
        if not CONFIG_DIR.exists():
            _seed_config_template(CONFIG_DIR)
        else:
            # Even if config/ exists, make sure commands/ subdir does.
            COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    else:
        # Dev: directories should already be there.
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        COMMANDS_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(value, fallback="device", max_length=80):
    """Convert user/configuration input into a safe single path component."""
    value = str(value or "").strip()
    value = value.replace("..", "_")
    value = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", value)
    value = re.sub(r"\s+", "_", value).strip(" ._")
    return (value or fallback)[:max_length]


def result_file_path(device_name, host, when=None):
    when = when or datetime.now()
    day_dir = LOG_DIR / when.strftime("%Y_%m_%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    stamp = when.strftime("%Y_%m_%d_%H_%M_%S_%f")
    unique = uuid4().hex[:8]
    filename = (safe_filename(device_name) + "_" +
                safe_filename(host) + "_" +
                stamp + "_" + unique + ".txt")
    return day_dir / filename


def open_in_file_manager(path):
    """Open a directory using the platform's file manager.

    Uses ``subprocess.run`` with an argument list so paths containing
    spaces or shell metacharacters are handled safely.  On Windows
    we still go through ``os.startfile`` which is the canonical way
    to ask Explorer to highlight a path.
    """
    resolved = str(path.resolve())
    if os.name == "nt":
        os.startfile(resolved)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        # "open" accepts a single path argument and treats it as a
        # literal path (no shell expansion needed).
        subprocess.run(["open", resolved], check=False)
        return
    # Linux / *BSD: hand off to xdg-open.  Use the array form so the
    # path is never re-parsed by a shell.
    subprocess.run(["xdg-open", resolved], check=False)


def find_favicon() -> "Path | None":
    """Return the absolute path to the bundled ``favicon.ico`` or
    ``None`` if the file cannot be found anywhere we know about.

    Single source of truth for the SDT logo.  Every UI surface that
    wants to render the favicon (TopBar brand mark, window/taskbar
    icon, etc.) calls this rather than re-deriving the path itself.

    Search order:
      1. ``BASE_DIR / "favicon.ico"``  -- project root in dev, or the
         directory next to the .exe in a frozen build.
      2. ``DATA_DIR / "favicon.ico"``  -- ``_MEIPASS`` in a frozen
         build (this is where PyInstaller extracts bundled data).

    Returns ``None`` if neither location has the file -- callers are
    expected to fall back to a plain label so the UI still launches
    when the favicon is missing.
    """
    for _base in (BASE_DIR, DATA_DIR):
        _p = _base / "favicon.ico"
        if _p.exists():
            return _p
    return None

