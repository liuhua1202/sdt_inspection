"""Transport adapters for SDT Telnet and SSH sessions.

The service layer depends on ``execute_device`` rather than on Tkinter or on a
specific Netmiko/Paramiko API.  This makes the connection code testable and
keeps protocol-specific details in one module.

Stop-event handling follows the pattern used by ``network_inspection``: every
blocking IO step is wrapped in ``_run_interruptible`` which runs the call in a
daemon thread.  The main code polls ``stop_event`` and force-closes the
underlying socket on demand so the daemon's blocking ``recv``/``read_channel``
returns immediately.  This guarantees that pressing the stop button reacts
within a few hundred milliseconds even when a worker is mid-command.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
import threading
from threading import Event
from typing import Any, Callable, Optional

from .models import CommandResult, Device, DeviceType
from .output import decode_bytes, filter_output, has_pagination, has_prompt, _is_login_prompt

# Module-level logger that goes through the same handler chain as
# ``logging_service.logger`` so the wide-except branches in this
# module leave a trace in the persistent log file (DEBUG level)
# without ever crashing the worker.  The application logger has
# already been configured by the time any transport code runs in
# a real launch, but a stand-alone ``import sdt_app.transport``
# in tests will not configure handlers -- the ``NullHandler``
# fallback keeps the calls safe.
_logger = logging.getLogger("sdt_app.transport")
if not _logger.handlers:
    _logger.addHandler(logging.NullHandler())

# Paramiko and Netmiko import a large dependency graph (30+ submodules).
# Importing them lazily from inside a worker thread triggers Python 3.12+
# ModuleLock deadlocks when several workers race to import the same
# module for the first time.  We import them once on the main thread
# the first time a worker asks, guarded by a lock so concurrent workers
# block briefly instead of deadlocking.
_import_lock = threading.Lock()
_paramiko = None
_netmiko = None


def _ensure_paramiko():
    """
    Lazily import paramiko on the first call, serialised by a lock.

    Importing paramiko for the first time pulls in 30+ submodules
    (`transport`, `util`, `config` ...).  When multiple
    worker threads do this in parallel, Python 3.12+ raises a
    `_DeadlockError` from the new per-module import lock.  We
    therefore perform the import exactly once, on the thread that
    gets here first; subsequent callers find `_paramiko` already
    populated and skip the import entirely.
    """
    global _paramiko
    if _paramiko is None:
        with _import_lock:
            if _paramiko is None:
                import paramiko
                _paramiko = paramiko
    return _paramiko

def _ensure_netmiko():
    """
    Same protection as :func:_ensure_paramiko for the Netmiko
    dependency.
    """
    global _netmiko
    if _netmiko is None:
        with _import_lock:
            if _netmiko is None:
                import netmiko
                _netmiko = netmiko
    return _netmiko


class TransportError(RuntimeError):
    pass


class InspectionCancelled(TransportError):
    pass


@dataclass(frozen=True)
class TransportOptions:
    encodings: tuple[str, ...] = ("utf-8", "gb18030", "gbk", "gb2312", "big5")
    connect_timeout: float = 15.0
    read_timeout: float = 15.0
    quiet_timeout: float = 0.8
    poll_interval: float = 0.05
    recv_timeout: float = 0.3
    # How long ``_run_interruptible`` will wait for the runner thread to exit
    # after force-closing the socket.  Kept small so the user-perceived stop
    # latency is bounded.
    abort_join_after: float = 0.3
    max_pages: int = 30
    strict_host_keys: bool = False


def _check_cancel(stop_event: Event) -> None:
    if stop_event.is_set():
        raise InspectionCancelled("巡检已被用户停止")


def _disconnect_fast(connection: Any, timeout: float = 0.3) -> None:
    """Best-effort, time-bounded ``close``/``disconnect``.

    ``client.close()`` or ``net_connect.disconnect()`` on a half-dead socket
    can hang on the OS TCP shutdown.  Running the call in a daemon thread
    with a join timeout prevents this from blocking the worker's stop path.
    """

    if connection is None:
        return

    def _runner() -> None:
        try:
            close = getattr(connection, "close", None)
            if not callable(close):
                close = getattr(connection, "disconnect", None)
            if callable(close):
                close()
        except Exception as exc:
            # We never want cleanup to raise; the worker is already
            # tearing down in response to a stop signal.  But we
            # still log the type so the persistent log file shows
            # what went wrong during the close, instead of leaving
            # operators guessing.
            _logger.debug(
                "_disconnect_fast: close raised %s", exc.__class__.__name__
            )

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout=timeout)


def _run_interruptible(
    func: Callable[[], Any],
    on_stop: Callable[[], None],
    stop_event: Event,
    poll_interval: float = 0.05,
    join_after: float = 0.3,
) -> Any:
    """Run ``func`` in a daemon thread, force-call ``on_stop`` on cancel.

    The pattern mirrors ``network_inspection``\u2019s ``_run_on_conn_interruptible``:

    1. ``func`` runs in a daemon thread (the runner).
    2. The caller thread polls ``stop_event`` at ``poll_interval``.
    3. As soon as ``stop_event`` is set, ``on_stop()`` is invoked (typically
       this force-closes the underlying socket so the runner's blocking IO
       returns immediately) and the caller joins the runner for at most
       ``join_after`` seconds before giving up.
    4. On normal completion the runner's return value is propagated; on
       cancellation ``InspectionCancelled`` is raised; any other exception
       from ``func`` is re-raised verbatim.

    This means every blocking call site in this module \u2014 ``client.connect``,
    ``_read_paramiko``, ``_read_netmiko`` \u2014 can be aborted within ~300 ms of
    the user pressing stop, regardless of how long the underlying network
    call would otherwise take.
    """

    if stop_event is not None and stop_event.is_set():
        raise InspectionCancelled("巡检已被用户停止")

    state: dict[str, Any] = {"value": None, "error": None, "done": False}

    def _runner() -> None:
        try:
            state["value"] = func()
        except BaseException as exc:  # noqa: BLE001 - intentionally broad
            state["error"] = exc
        finally:
            state["done"] = True

    runner = threading.Thread(target=_runner, daemon=True)
    runner.start()

    force_stopped = False
    while not state["done"]:
        if stop_event is not None and stop_event.is_set():
            try:
                on_stop()
            except Exception:
                # The on_stop hook itself failing must not block the cancel.
                pass
            runner.join(timeout=join_after)
            force_stopped = True
            break
        runner.join(timeout=poll_interval)

    if force_stopped:
        raise InspectionCancelled("巡检已被用户停止")
    error = state["error"]
    if error is not None:
        raise error
    return state["value"]


def _read_paramiko(
    channel,
    options: TransportOptions,
    stop_event: Event,
) -> str:
    output = ""
    deadline = time.monotonic() + options.read_timeout
    quiet_deadline: float | None = None
    while time.monotonic() < deadline:
        if stop_event.is_set():
            raise InspectionCancelled("\u5de1\u68c0\u5df2\u88ab\u7528\u6237\u505c\u6b62")
        try:
            ready = channel.recv_ready()
        except Exception as exc:
            # ``recv_ready`` on a closed Paramiko channel can raise
            # ``EOFError`` / socket errors.  Treat as "nothing to
            # read" but log the type so a misbehaving device shows
            # up in the persistent log instead of being invisible.
            _logger.debug(
                "_read_paramiko: recv_ready raised %s", exc.__class__.__name__
            )
            ready = False
        if ready:
            try:
                data = channel.recv(4096)
            except socket.timeout:
                # Paramiko uses a non-blocking poll underneath, so this
                # branch is the normal idle path.  Continue the loop so the
                # quiet_deadline logic can decide whether to keep waiting
                # rather than accidentally treating idle as EOF.
                data = b""
            except (OSError, EOFError):
                # Connection closed underneath us — treat as cancel if the
                # user asked to stop, otherwise propagate.
                if stop_event.is_set():
                    raise InspectionCancelled("巡检已被用户停止")
                break
            if not data:
                # Empty bytes AFTER a non-timeout read is a real EOF on
                # Paramiko channels; bail out (but only if the user has
                # not asked to stop).  The socket.timeout branch above is
                # the normal idle path; this one is the actual close.
                if stop_event.is_set():
                    raise InspectionCancelled("巡检已被用户停止")
                break
            output += decode_bytes(data, options.encodings)
            # Once stop has been requested, shrink the quiet-wait so we exit
            # on the next loop iteration instead of waiting out the full
            # quiet_timeout while the user is staring at the UI.
            quiet_wait = options.quiet_timeout if not stop_event.is_set() else 0.05
            quiet_deadline = time.monotonic() + quiet_wait
            if has_prompt(output) and not has_pagination(output):
                deadline = min(deadline, quiet_deadline + 0.2)
        elif quiet_deadline is not None and (
            time.monotonic() >= quiet_deadline or stop_event.is_set()
        ):
            break
        else:
            time.sleep(options.poll_interval)
    if stop_event.is_set():
        raise InspectionCancelled("\u5de1\u68c0\u5df2\u88ab\u7528\u6237\u505c\u6b62")
    return output


def _read_netmiko(
    connection,
    options: TransportOptions,
    stop_event: Event,
) -> str:
    output = ""
    deadline = time.monotonic() + options.read_timeout
    quiet_deadline: float | None = None
    while time.monotonic() < deadline:
        if stop_event.is_set():
            raise InspectionCancelled("\u5de1\u68c0\u5df2\u88ab\u7528\u6237\u505c\u6b62")
        try:
            chunk = connection.read_channel()
        except Exception as exc:
            _logger.debug(
                "_read_netmiko: read_channel raised %s",
                exc.__class__.__name__,
            )
            if stop_event.is_set():
                raise InspectionCancelled("\u5de1\u68c0\u5df2\u88ab\u7528\u6237\u505c\u6b62")
            break
        if chunk:
            output += decode_bytes(chunk, options.encodings)
            quiet_wait = options.quiet_timeout if not stop_event.is_set() else 0.05
            quiet_deadline = time.monotonic() + quiet_wait
            if has_prompt(output) and not has_pagination(output):
                deadline = min(deadline, quiet_deadline + 0.2)
        elif quiet_deadline is not None and (
            time.monotonic() >= quiet_deadline or stop_event.is_set()
        ):
            break
        else:
            time.sleep(options.poll_interval)
    if stop_event.is_set():
        raise InspectionCancelled("\u5de1\u68c0\u5df2\u88ab\u7528\u6237\u505c\u6b62")
    return output


def _collect_pages_netmiko(connection, output: str, options: TransportOptions, stop_event: Event) -> str:
    for _ in range(options.max_pages):
        _check_cancel(stop_event)
        if not has_pagination(output):
            break
        connection.write_channel(" ")
        time.sleep(options.poll_interval)
        more = _read_netmiko(connection, options, stop_event)
        output += more
        if not more:
            break
    return output


def _collect_pages_paramiko(channel, output: str, options: TransportOptions, stop_event: Event) -> str:
    for _ in range(options.max_pages):
        _check_cancel(stop_event)
        if not has_pagination(output):
            break
        channel.send(b" ")
        time.sleep(options.poll_interval)
        more = _read_paramiko(channel, options, stop_event)
        output += more
        if not more:
            break
    return output


def _execute_netmiko(
    device: Device,
    device_type: DeviceType,
    commands: list[str],
    options: TransportOptions,
    stop_event: Event,
    connection_tracker: Any = None,
) -> list[CommandResult]:
    netmiko = _ensure_netmiko()
    ConnectHandler = netmiko.ConnectHandler

    protocol = device.resolved_protocol(device_type)
    params = {
        "device_type": device_type.driver(protocol),
        "host": device.host,
        "port": device.port,
        "timeout": options.connect_timeout,
        "read_timeout_override": options.read_timeout,
        "global_delay_factor": 1,
    }
    if device.username:
        params["username"] = device.username
    if device.password:
        params["password"] = device.password
    # SDT does not need enable (DEFAULT_SDT_TYPE.needs_enable is
    # always False), and the legacy ``Device.enable_password``
    # field was removed in the SDT-only refactor.  Operators who
    # fork the project to add a new device type can reintroduce
    # the enable handshake here.

    # Wrap the initial ConnectHandler so stop_event can interrupt it.
    connection = _run_interruptible(
        lambda: ConnectHandler(**params),
        lambda: None,  # nothing to close yet \u2014 nothing was opened
        stop_event,
        poll_interval=options.poll_interval,
        join_after=options.abort_join_after,
    )
    if connection_tracker is not None:
        connection_tracker.register(connection)

    def _abort_netmiko() -> None:
        _disconnect_fast(connection, timeout=options.abort_join_after)

    def _read_abortable() -> str:
        return _read_netmiko(connection, options, stop_event)

    def _read_command(command: str) -> str:
        connection.write_channel(command + "\r\n")
        output = _read_netmiko(connection, options, stop_event)
        return _collect_pages_netmiko(connection, output, options, stop_event)

    results: list[CommandResult] = []
    try:
        # Same prompt-await loop as the Paramiko path: drain then
        # nudge up to three times.
        initial = ""
        for _ in range(3):
            initial += _run_interruptible(_read_abortable, _abort_netmiko, stop_event)
            if has_prompt(initial):
                break
            connection.write_channel("\r\n")
        else:
            raise TransportError("\u8fde\u63a5\u6210\u529f\u4f46\u672a\u68c0\u6d4b\u5230\u8bbe\u5907\u547d\u4ee4\u63d0\u793a\u7b26")

        # SDT pre-auth shell detection.  Netmiko's connect handler
        # already accepted the (operator-supplied) telnet credentials,
        # but the device only lets the operator in to a "please login
        # as:" shell that displays the literal hint
        # ``login <user> <password>``.  Without this branch every
        # command we send is echoed back inside the same
        # "please login as:" / ``[SDT-test]`` block and the
        # inspection file ends up as a wall of login hints.  See
        # ``_is_login_prompt`` in ``output.py`` for the patterns
        # we recognise.
        if _is_login_prompt(initial):
            if not device.username or not device.password:
                raise TransportError(
                    "\u8bbe\u5907\u8981\u6c42\u767b\u5f55\u9a8c\u8bc1\uff0c\u4f46\u6ca1\u6709\u914d\u7f6e\u7528\u6237\u540d\u6216\u5bc6\u7801"
                )
            connection.write_channel(
                f"login {device.username} {device.password}\r\n"
            )
            login_output = _run_interruptible(
                _read_abortable, _abort_netmiko, stop_event,
            )
            if not has_prompt(login_output):
                raise TransportError("\u8bbe\u5907\u7528\u6237\u9a8c\u8bc1\u5931\u8d25")

        # SDT does not need enable.  If you fork the project to add
        # a device type that does, reintroduce the enable handshake
        # here against ``device_type.needs_enable``.
        if device_type.disable_paging_command:
            connection.write_channel(device_type.disable_paging_command + "\r\n")
            _run_interruptible(_read_abortable, _abort_netmiko, stop_event)

        for command in commands:
            _check_cancel(stop_event)
            output = _run_interruptible(
                lambda cmd=command: _read_command(cmd),
                _abort_netmiko,
                stop_event,
            )
            results.append(CommandResult(command=command, output=filter_output(output, command)))
        try:
            connection.write_channel("exit\r\n")
        except Exception:
            pass
        return results
    finally:
        if connection_tracker is not None:
            connection_tracker.unregister(connection)
        _disconnect_fast(connection, timeout=options.abort_join_after)


# SSH key file names we will probe, in order, when password
# auth is rejected by the device.  ~/.ssh is the operator's
# standard location on every platform; the project-side
# config/ directory lets a per-installation key be dropped
# next to devices.csv.  ``id_ed25519`` is preferred because
# it is the current OpenSSH default; ``id_rsa`` is the
# historical fallback.
_SSH_KEY_FILENAMES = ("id_ed25519", "id_rsa", "id_ecdsa")

# SDT devices accept only a hard-coded pre-auth SSH account
# (``sdt`` / ``123456``) at the SSH layer.  The operator's
# own credentials from ``devices.csv`` are reserved for the
# *second-stage* ``login <user> <pass>`` command that the
# pre-auth shell demands (recognised by a prompt ending in
# ``]``).  Do not let the device-supplied username/password
# leak into the SSH handshake -- the device's sshd will
# reject them.
#
# The ``123456`` password was confirmed by the operator on a
# live SDT-Device-02 on 2026-07-31.  A test
# (``test_sdt_preauth_password_matches_documented_value``)
# locks in this value so a careless edit shows up in CI
# before it ships.  If the device vendor ever changes the
# pre-auth password, update BOTH the constant AND the test
# after re-verifying on hardware.
SDT_SSH_USERNAME = "sdt"
SDT_SSH_PASSWORD = "123456"


def _candidate_ssh_key_paths():
    """Return the well-known locations an SDT operator might
    have placed their private key.  The list is generated on
    each call so a freshly copied key (e.g. into config/) is
    picked up on the next inspection without restarting the app.
    """
    from .paths import BASE_DIR, DATA_DIR
    home = Path.home()
    out = []
    for name in _SSH_KEY_FILENAMES:
        out.append(home / ".ssh" / name)
    for base in (BASE_DIR, DATA_DIR):
        for name in _SSH_KEY_FILENAMES:
            out.append(base / "config" / name)
    return out


def _try_load_default_ssh_key(paramiko_module):
    """Return the first usable SSH key in the candidate
    paths, or ``None`` if no key exists / every key is
    encrypted / every load fails for any reason.
    """
    for path in _candidate_ssh_key_paths():
        if not path.is_file():
            continue
        for loader in (
            paramiko_module.Ed25519Key,
            paramiko_module.RSAKey,
            paramiko_module.ECDSAKey,
        ):
            try:
                return loader.from_private_key_file(str(path))
            except paramiko_module.PasswordRequiredException:
                # Encrypted key without a passphrase in our
                # prompt.  Skip; the operator must remove the
                # passphrase (``ssh-keygen -p``) or use ssh-agent.
                break
            except Exception:
                continue
    return None


def _execute_ssh(
    device: Device,
    device_type: DeviceType,
    commands: list[str],
    options: TransportOptions,
    stop_event: Event,
    log_warning=None,
    connection_tracker: Any = None,
) -> list[CommandResult]:
    paramiko = _ensure_paramiko()

    client = paramiko.SSHClient()
    if connection_tracker is not None:
        connection_tracker.register(client)
    try:
        client.load_system_host_keys()
        if options.strict_host_keys:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            # Legacy SDT compatibility: auto-accept unknown hosts.
            # The UI surfaces this as a single startup notice instead
            # of warning on every connection.  Set
            # SDT_STRICT_HOST_KEYS=1 (or toggle the toolbar switch)
            # to enable strict verification.
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_args = {
            "hostname": device.host,
            "port": device.port,
            # SDT devices only accept a fixed pre-auth account at
            # the SSH layer (``SDT_SSH_USERNAME`` / ``SDT_SSH_PASSWORD``).
            # The operator's ``device.username`` / ``device.password``
            # are kept for the second-stage ``login <user> <pass>``
            # command issued after the pre-auth shell appears.
            "username": SDT_SSH_USERNAME,
            "password": SDT_SSH_PASSWORD,
            "timeout": options.connect_timeout,
            "look_for_keys": False,
            "allow_agent": False,
        }
        try:
            _run_interruptible(
                lambda: client.connect(**connect_args),
                lambda: _disconnect_fast(client, timeout=options.abort_join_after),
                stop_event,
                poll_interval=options.poll_interval,
                join_after=options.abort_join_after,
            )
        except InspectionCancelled:
            raise
        except paramiko.BadAuthenticationType as exc:
            # The device's kex-init only advertised auth methods
            # we did not offer (typically ``publickey`` while we
            # sent ``password``).  Look for a default SSH key in
            # the operator's standard locations and retry with
            # ``pkey=``; if no key is available, surface a clear,
            # actionable error instead of Paramiko's one-liner.
            #
            # Catching by exception type (not by message match)
            # is deliberate: future Paramiko versions are free to
            # rephrase the explanation string, but
            # ``BadAuthenticationType`` is part of the public API
            # and also gives us ``allowed_types`` / ``types_tried``
            # for richer diagnostics later.
            key = _try_load_default_ssh_key(paramiko)
            if key is not None:
                key_args = dict(connect_args)
                key_args.pop("password", None)
                key_args["pkey"] = key
                try:
                    _run_interruptible(
                        lambda: client.connect(**key_args),
                        lambda: _disconnect_fast(
                            client,
                            timeout=options.abort_join_after,
                        ),
                        stop_event,
                        poll_interval=options.poll_interval,
                        join_after=options.abort_join_after,
                    )
                except InspectionCancelled:
                    raise
                except Exception as exc2:
                    # Chain to the *new* failure (key auth), not
                    # back to the original ``No auth methods``
                    # trigger -- the operator needs to see the
                    # real reason the key path failed (wrong key,
                    # server rejected the public half, etc.).
                    raise TransportError(
                        f"SSH \u8fde\u63a5\u5931\u8d25: \u5bc6\u7801\u88ab\u670d\u52a1\u5668\u62d2\u7edd\uff0c"
                        f"\u9a8c\u8bc1\u5bc6\u94a5\u4e5f\u5931\u8d25 ({exc2})"
                    ) from exc2
            else:
                raise TransportError(
                    "SSH \u8fde\u63a5\u5931\u8d25: \u670d\u52a1\u5668\u62d2\u7edd\u5bc6\u7801\u8ba4\u8bc1\uff0c"
                    "\u8bf7\u5c06\u79c1\u94a5\u653e\u5230\u4ee5\u4e0b\u4efb\u4e00\u4f4d\u7f6e: "
                    "~/.ssh/id_ed25519\u3001~/.ssh/id_rsa\u3001"
                    "<exe-dir>/config/id_ed25519 \u6216 id_rsa\u3002"
                    "\u5982\u679c\u5bc6\u94a5\u5e26\u53e3\u4ee4\uff0c"
                    "\u8bf7\u7528 ssh-keygen -p \u53bb\u6389\u53e3\u4ee4\u6216\u4f7f\u7528 ssh-agent\u3002"
                ) from exc
        except Exception as exc:
            raise TransportError(f"SSH \u8fde\u63a5\u5931\u8d25: {exc}") from exc

        channel = _run_interruptible(
            client.invoke_shell,
            lambda: _disconnect_fast(client, timeout=options.abort_join_after),
            stop_event,
            poll_interval=options.poll_interval,
            join_after=options.abort_join_after,
        )
        # Short recv timeout so the stop_event poll wakes up quickly.
        channel.settimeout(options.recv_timeout)

        def _abort_ssh() -> None:
            _disconnect_fast(client, timeout=options.abort_join_after)

        def _read_abortable() -> str:
            return _read_paramiko(channel, options, stop_event)

        def _read_command(command: str) -> str:
            channel.send((command + "\r\n").encode())
            output = _read_paramiko(channel, options, stop_event)
            return _collect_pages_paramiko(channel, output, options, stop_event)

        try:
            time.sleep(0.1)
            channel.send(b"\r\n")
            output = _run_interruptible(_read_abortable, _abort_ssh, stop_event)
            if not has_prompt(output):
                channel.send(b"\r\n")
                output += _run_interruptible(_read_abortable, _abort_ssh, stop_event)
            if not has_prompt(output):
                raise TransportError("SSH \u8fde\u63a5\u6210\u529f\u4f46\u672a\u68c0\u6d4b\u5230\u8bbe\u5907\u547d\u4ee4\u63d0\u793a\u7b26")

            if _is_login_prompt(output):
                if not device.username or not device.password:
                    raise TransportError("\u8bbe\u5907\u8981\u6c42\u767b\u5f55\u9a8c\u8bc1\uff0c\u4f46\u6ca1\u6709\u914d\u7f6e\u7528\u6237\u540d\u6216\u5bc6\u7801")
                channel.send(f"login {device.username} {device.password}\r\n".encode())
                login_output = _run_interruptible(_read_abortable, _abort_ssh, stop_event)
                if not has_prompt(login_output):
                    raise TransportError("\u8bbe\u5907\u7528\u6237\u9a8c\u8bc1\u5931\u8d25")

            # SDT does not need enable.  If you fork the project to add
            # a device type that does, reintroduce the enable handshake
            # here against ``device_type.needs_enable``.
            if device_type.disable_paging_command:
                channel.send((device_type.disable_paging_command + "\r\n").encode())
                _run_interruptible(_read_abortable, _abort_ssh, stop_event)

            results: list[CommandResult] = []
            for command in commands:
                _check_cancel(stop_event)
                command_output = _run_interruptible(
                    lambda cmd=command: _read_command(cmd),
                    _abort_ssh,
                    stop_event,
                )
                results.append(
                    CommandResult(command=command, output=filter_output(command_output, command))
                )
            try:
                channel.send(b"exit\r\n")
            except Exception:
                pass
            return results
        finally:
            try:
                channel.close()
            except Exception:
                pass
    finally:
        if connection_tracker is not None:
            connection_tracker.unregister(client)
        try:
            client.close()
        except Exception:
            pass


def execute_device(
    device: Device,
    device_type: DeviceType,
    commands: list[str],
    options: TransportOptions,
    stop_event: Event,
    log_warning=None,
    connection_tracker: Any = None,
) -> list[CommandResult]:
    if not commands:
        raise TransportError("\u6ca1\u6709\u53ef\u6267\u884c\u7684\u5de1\u68c0\u547d\u4ee4")
    protocol = device.resolved_protocol(device_type)
    if protocol == "ssh":
        # SDT uses an interactive Paramiko shell; standard network device
        # types can use their configured Netmiko SSH driver.
        if device_type.ssh_driver and device_type.ssh_driver.lower() != "paramiko":
            return _execute_netmiko(
                device, device_type, commands, options, stop_event,
                connection_tracker,
            )
        return _execute_ssh(
            device, device_type, commands, options, stop_event,
            log_warning, connection_tracker,
        )
    return _execute_netmiko(
        device, device_type, commands, options, stop_event,
        connection_tracker,
    )