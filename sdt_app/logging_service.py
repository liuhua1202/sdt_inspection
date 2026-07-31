"""Application logging that is safe to call from worker threads."""

from __future__ import annotations

import logging
import queue
import re
from datetime import datetime
from typing import Iterable

from .models import InspectionEvent
from .paths import LOG_FILE_DIR, ensure_directories

# Match ``key=value`` / ``key: value`` / ``key 'value'`` for known
# credential fields.  The leading group is preserved so a log line
# still reads ``password=****`` instead of being completely blanked.
_REDACT_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b"
    r"(\s*[:=]\s*[\"']?)([^\s\"',;}]+)([\"']?)"
)
# Catch Paramiko / Netmiko style "with password 'xxx'" / "password xxx".
_REDACT_PHRASE_RE = re.compile(
    r"(?i)(with\s+password\s+|password\s+is\s+|password\s*[:=]\s*)"
    r"[\"']?([^\s\"',;}]+)[\"']?"
)
_REDACT_TOKEN_LIKE = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"
)

REDACT_PLACEHOLDER = "****"


def redact_sensitive(message: str, extra_values: Iterable[str] = ()) -> str:
    """Scrub credential-shaped substrings from ``message``.

    The function is intentionally permissive: it errs on the side of
    redacting things that *look* like a credential so a real password
    never reaches the persistent ``all_logs_*.log`` file.  Operators
    still get the surrounding context (``auth failed for user admin``)
    which is enough to debug without leaking the secret.
    """
    if not message:
        return message
    text = str(message)
    text = _REDACT_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{REDACT_PLACEHOLDER}{m.group(4)}",
        text,
    )
    text = _REDACT_PHRASE_RE.sub(
        lambda m: f"{m.group(1)}{REDACT_PLACEHOLDER}",
        text,
    )
    text = _REDACT_TOKEN_LIKE.sub(
        lambda m: f"{m.group(1)}{REDACT_PLACEHOLDER}",
        text,
    )
    # Also scrub any explicit value the caller hands in (e.g. the
    # device's own password) so it never ends up in a traceback.
    for value in extra_values:
        if not value:
            continue
        token = str(value)
        if not token or token == REDACT_PLACEHOLDER:
            continue
        text = text.replace(token, REDACT_PLACEHOLDER)
    return text

logger = logging.getLogger("sdt_inspection")
logger.setLevel(logging.DEBUG)
logger.propagate = False

if not logger.handlers:
    ensure_directories()
    _stamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    _file_handler = logging.FileHandler(
        LOG_FILE_DIR / f"all_logs_{_stamp}.log", encoding="utf-8"
    )
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(_file_handler)
    _console = logging.StreamHandler()
    _console.setLevel(logging.INFO)
    _console.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    logger.addHandler(_console)



class AppLogger:
    def __init__(self, event_queue=None):
        self.events = event_queue
        self.logger = logger
        # DEBUG stays in the file handler for post-mortem;
        # it is hidden from the runtime log panel because it
        # is mostly tracebacks and protocol noise.
        self.UI_MIN_LEVEL = logging.INFO

    @staticmethod
    def _summarise_for_ui(message):
        """
        Shorten a Python traceback to the one or two lines that
        actually help the operator: the final exception type and
        message, optionally prefixed with the originating file:line.

        Multi-line messages that are NOT tracebacks are passed
        through untouched so we never drop user-facing context.
        """
        if "Traceback (most recent call last):" not in message:
            return message
        last_error = ""
        last_file = ""
        for raw in message.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("File "):
                last_file = line
            elif line == "Traceback (most recent call last):":
                continue
            else:
                last_error = line
        if last_error:
            return f"{last_file} -> {last_error}" if last_file else last_error
        return message



    def _write(self, level, message, device_name="", sensitive=()):
        safe_message = redact_sensitive(message, sensitive)
        self.logger.log(level, safe_message)
        if self.events is not None and level >= self.UI_MIN_LEVEL:
            try:
                self.events.put_nowait(
                    InspectionEvent(
                        kind="log",
                        message=self._summarise_for_ui(safe_message),
                        device_name=device_name,
                    )
                )
            except queue.Full:
                # UI is backed up; the persistent log file still
                # has the record, so dropping the live view is
                # acceptable.  We deliberately do not even log a
                # debug line here because the logger itself is
                # often the source of the very events we are
                # trying to enqueue.
                pass

    def debug(self, message: str, device_name: str = "", sensitive=()) -> None:
        self._write(logging.DEBUG, message, device_name, sensitive)

    def info(self, message: str, device_name: str = "", sensitive=()) -> None:
        self._write(logging.INFO, message, device_name, sensitive)

    def warning(self, message: str, device_name: str = "", sensitive=()) -> None:
        self._write(logging.WARNING, message, device_name, sensitive)

    def error(self, message: str, device_name: str = "", sensitive=()) -> None:
        self._write(logging.ERROR, message, device_name, sensitive)

    def exception(
        self,
        message: str,
        device_name: str = "",
        sensitive=(),
    ) -> None:
        # ``logger.exception`` formats the active exception into the
        # log record.  The active exception's own text is already
        # covered by ``redact_sensitive`` when callers pass
        # ``str(exc)``; this path catches the rare case where the
        # exception object itself contains a password-like attribute
        # that Python's default formatter walks over.
        self.logger.exception(message)
        if self.events is not None:
            try:
                self.events.put_nowait(
                    InspectionEvent(
                        kind="log",
                        message=self._summarise_for_ui(
                            redact_sensitive(message, sensitive)
                        ),
                        device_name=device_name,
                    )
                )
            except queue.Full:
                pass
