"""Threaded inspection orchestration, independent of the Tkinter UI."""

from __future__ import annotations

import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from queue import Full, Queue
from threading import Event, Lock, Thread
from typing import Callable

from .logging_service import AppLogger
from .models import (
    DEFAULT_SDT_TYPE,
    Device,
    DeviceType,
    InspectionEvent,
    InspectionResult,
    ResultStatus,
)
from .paths import result_file_path
from .transport import (
    InspectionCancelled,
    TransportOptions,
    execute_device,
)




class _ConnectionTracker:
    """Track active transport connections so ``stop()`` can close them.

    Both Paramiko ``SSHClient`` instances and Netmiko connection objects
    expose a ``close``/``disconnect`` method.  Registering them on open and
    unregistering on teardown lets the service proactively close every live
    socket when the user presses the stop button.  Closing the underlying
    socket causes any blocking ``recv`` / ``read_channel`` call inside the
    worker threads to return immediately instead of waiting out the full
    read timeout.
    """

    # Per-connection close budget.  A hung ``net_connect.disconnect()``
    # on Windows can wait many seconds for the TCP shutdown handshake;
    # keeping the per-connection budget low caps the total ``close_all``
    # latency at ``timeout_per_connection * n_connections`` worst case
    # but in practice each daemon thread exits in a few hundred ms.
    CLOSE_TIMEOUT = 0.5

    def __init__(self) -> None:
        self._connections: list[object] = []
        self._lock = Lock()

    def register(self, connection: object) -> None:
        with self._lock:
            self._connections.append(connection)

    def unregister(self, connection: object) -> None:
        with self._lock:
            try:
                self._connections.remove(connection)
            except ValueError:
                pass

    def _close_one(self, connection: object) -> None:
        # Resolve the close method first so we can use the same
        # priority order Paramiko -> Netmiko as the rest of the
        # service.  We always run the actual ``close``/``disconnect``
        # call in a daemon thread with a join timeout; this prevents
        # a single stuck socket from blocking the stop path for the
        # full TCP shutdown timeout (which on Windows can be 5+ s).
        close = getattr(connection, "close", None)
        if not callable(close):
            close = getattr(connection, "disconnect", None)
        if not callable(close):
            return

        def _runner() -> None:
            try:
                close()
            except Exception:
                # Best-effort cleanup: stopping must never raise
                # from here.
                pass

        thread = Thread(
            target=_runner,
            name=f"connection-close-{id(connection)}",
            daemon=True,
        )
        thread.start()
        thread.join(timeout=self.CLOSE_TIMEOUT)

    def close_all(self) -> None:
        with self._lock:
            connections = list(self._connections)
            # Drop the references so a second close_all() call is a
            # no-op.  Workers that subsequently call ``unregister`` will
            # silently succeed via the existing ValueError fallback.
            self._connections.clear()
        for connection in connections:
            self._close_one(connection)

class InspectionService:
    """Run selected devices and publish progress through a thread-safe queue."""

    def __init__(
        self,
        event_queue: Queue[InspectionEvent],
        result_dir: Path | None = None,
        executor: Callable = execute_device,
    ) -> None:
        self.events = event_queue
        self.logger = AppLogger(event_queue)
        self.result_dir = result_dir
        self.executor = executor
        self.stop_event = Event()
        self.connections = _ConnectionTracker()
        self._thread: Thread | None = None
        self._state_lock = Lock()
        self._running = False

    @property
    def running(self) -> bool:
        with self._state_lock:
            return self._running

    def start(
        self,
        devices: list[Device],
        device_types: dict[str, DeviceType],
        commands_by_type: dict[str, list[str]],
        concurrency: int,
        encodings: tuple[str, ...],
        strict_host_keys: bool = False,
    ) -> None:
        # Take the state lock for the whole start sequence.  This
        # serialises with concurrent ``stop`` calls (the UI is
        # single-threaded today, but the same service can be driven
        # by a future scheduler thread or a test harness) so that
        # ``stop_event`` is cleared *before* ``_running`` is
        # observable, and so that any failure between setting
        # ``_running`` and actually starting the thread is
        # correctly rolled back.
        with self._state_lock:
            if self._running:
                raise RuntimeError("巡检任务正在运行")
            self._running = True
            self.stop_event.clear()
        try:
            selected = [replace(device) for device in devices if device.selected]
            if strict_host_keys:
                self.logger.info("主机密钥校验已启用 (RejectPolicy)")
            else:
                self.logger.info(
                    "主机密钥校验未启用 (AutoAddPolicy); 可在工具栏切换或设置 SDT_STRICT_HOST_KEYS=1",
                )
            self._thread = Thread(
                target=self._run,
                args=(selected, device_types, commands_by_type, concurrency,
                      encodings, strict_host_keys),
                name="inspection-coordinator",
                daemon=True,
            )
            self._thread.start()
        except BaseException:
            # Roll back the running flag so a future ``start`` call
            # does not get a spurious "already running" error.  We
            # also clear the stop_event because ``stop`` may have
            # raced with us and set it; if it did, the next start
            # would otherwise exit immediately as cancelled.
            with self._state_lock:
                self._running = False
                self.stop_event.clear()
            raise

    def stop(self, join=False, join_timeout=5.0):
        if not self.running:
            return
        self.logger.info("正在停止巡检，立即断开所有连接")
        # Close every live transport socket first so that any blocking
        # recv/read_channel returns immediately instead of waiting out
        # the read timeout.  This is what makes the stop action feel
        # instantaneous even when workers are mid-command.
        self.connections.close_all()
        self.stop_event.set()
        if join and self._thread is not None:
            self._thread.join(timeout=join_timeout)

    def _emit(self, event: InspectionEvent) -> None:
        # Use ``put_nowait`` against a bounded queue so a frozen UI
        # thread cannot make workers grow the queue without bound.
        # The persistent log file is the source of truth; the UI
        # queue is a transient view that is allowed to drop
        # intermediate events when the operator is busy with a
        # dialog.
        try:
            self.events.put_nowait(event)
        except Full:
            pass

    def _commands_for(
        self,
        device: Device,
        commands_by_type: dict[str, list[str]],
    ) -> list[str]:
        return list(
            commands_by_type.get(device.type_id)
            or commands_by_type.get("sdt")
            or next(iter(commands_by_type.values()), [])
        )

    def _run_device(
        self,
        device: Device,
        device_types: dict[str, DeviceType],
        commands_by_type: dict[str, list[str]],
        encodings: tuple[str, ...],
        strict_host_keys: bool = False,
    ) -> InspectionResult:
        started_at = datetime.now()
        device_type = (
            device_types.get(device.type_id)
            or device_types.get(DEFAULT_SDT_TYPE.type_id)
            or DEFAULT_SDT_TYPE
        )
        commands = self._commands_for(device, commands_by_type)
        log_path = result_file_path(device.name, device.host, started_at)
        # Pass the device's secrets as ``sensitive`` so the logger
        # scrubs them out of any traceback or exception text.  We
        # only do this for the per-device log path: shared events
        # (start/stop of the whole job) intentionally do not see
        # credentials.
        device_secrets = (device.password, device.enable_password)
        self._emit(
            InspectionEvent(
                kind="device_started",
                message=f"开始巡检: {device.name} ({device.host})",
                device_name=device.name,
            )
        )
        self.logger.info(
            f"开始处理设备 {device.name} ({device.host})",
            device.name,
        )

        status = ResultStatus.SUCCESS
        error = ""
        command_results = []
        try:
            if self.stop_event.is_set():
                raise InspectionCancelled("巡检已被用户停止")
            options = TransportOptions(
                encodings=encodings,
                strict_host_keys=strict_host_keys,
            )
            command_results = self.executor(
                device,
                device_type,
                commands,
                options,
                self.stop_event,
                lambda message: self.logger.warning(
                    message, device.name, device_secrets,
                ),
                self.connections,
            )
        except InspectionCancelled as exc:
            status = ResultStatus.CANCELLED
            error = str(exc)
        except Exception as exc:  # connection libraries expose many exception types
            status = ResultStatus.FAILED
            error = str(exc) or exc.__class__.__name__
            self.logger.error(
                f"设备 {device.name} 巡检失败: {error}",
                device.name,
                device_secrets,
            )
            self.logger.debug(
                traceback.format_exc(),
                device.name,
                device_secrets,
            )

        finished_at = datetime.now()
        result = InspectionResult(
            device=device,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            command_results=command_results,
            log_file=log_path,
            error=error,
        )
        try:
            self._write_result(result)
        except OSError as exc:
            self.logger.error(f"设备 {device.name} 结果文件写入失败: {exc}", device.name)
            result.log_file = None
        return result

    def _write_result(self, result: InspectionResult) -> None:
        if result.log_file is None:
            return
        result.log_file.parent.mkdir(parents=True, exist_ok=True)
        device = result.device
        with result.log_file.open("w", encoding="utf-8") as output:
            output.write(f"设备名称: {device.name}\n")
            output.write(f"地址: {device.host}\n")
            output.write(f"设备类型: {device.type_id}\n")
            output.write(f"协议: {device.protocol.upper()}\n")
            output.write(f"端口: {device.port}\n")
            output.write(f"用户名: {device.username}\n")
            output.write("密码: ****\n")
            output.write(f"开始时间: {result.started_at:%Y-%m-%d %H:%M:%S}\n")
            output.write(f"结束时间: {result.finished_at:%Y-%m-%d %H:%M:%S}\n")
            output.write(f"状态: {result.status.value}\n")
            if result.error:
                output.write(f"错误: {result.error}\n")
            output.write("=" * 70 + "\n\n")
            for command_result in result.command_results:
                output.write(f"执行命令: {command_result.command}\n")
                output.write("-" * 70 + "\n")
                output.write(command_result.output)
                if command_result.output and not command_result.output.endswith("\n"):
                    output.write("\n")
                output.write("\n")

    def _run(
        self,
        selected: list[Device],
        device_types: dict[str, DeviceType],
        commands_by_type: dict[str, list[str]],
        concurrency: int,
        encodings: tuple[str, ...],
        strict_host_keys: bool = False,
    ) -> None:
        total = len(selected)
        completed = 0
        success = 0
        failed = 0
        cancelled = 0
        if not selected:
            self._emit(InspectionEvent(kind="finished", message="没有选中的设备", total=0))
            with self._state_lock:
                self._running = False
            return

        self._emit(
            InspectionEvent(
                kind="started",
                message=f"开始巡检，共 {total} 台设备，并发数 {concurrency}",
                total=total,
            )
        )
        futures: dict[Future[InspectionResult], Device] = {}
        try:
            with ThreadPoolExecutor(
                max_workers=max(1, min(concurrency, total)),
                thread_name_prefix="inspection-device",
            ) as pool:
                for device in selected:
                    future = pool.submit(
                        self._run_device,
                        device,
                        device_types,
                        commands_by_type,
                        encodings,
                        strict_host_keys,
                    )
                    futures[future] = device
                for future in as_completed(futures):
                    device = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = InspectionResult(
                            device=device,
                            status=ResultStatus.FAILED,
                            started_at=datetime.now(),
                            finished_at=datetime.now(),
                            error=str(exc),
                        )
                    completed += 1
                    if result.status is ResultStatus.SUCCESS:
                        success += 1
                    elif result.status is ResultStatus.CANCELLED:
                        cancelled += 1
                    else:
                        failed += 1
                    self._emit(
                        InspectionEvent(
                            kind="device_finished",
                            message=f"{device.name}: {result.status.value}",
                            device_name=device.name,
                            completed=completed,
                            total=total,
                            result=result,
                        )
                    )
                    self._emit(
                        InspectionEvent(
                            kind="progress",
                            message=f"已完成 {completed}/{total}",
                            completed=completed,
                            total=total,
                        )
                    )
        except Exception as exc:
            self.logger.exception(f"巡检协调线程异常: {exc}")
        finally:
            message = (
                f"巡检完成: 共 {total} 台，成功 {success} 台，失败 {failed} 台，"
                f"已取消 {cancelled} 台"
            )
            self._emit(
                InspectionEvent(
                    kind="finished",
                    message=message,
                    completed=completed,
                    total=total,
                )
            )
            self.logger.info(message)
            with self._state_lock:
                self._running = False
