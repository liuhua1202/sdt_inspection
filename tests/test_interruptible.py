"""Tests for the interruptible wrapper that mirrors network_inspection.

These tests verify that ``_run_interruptible`` can abort a blocking call
within a few hundred milliseconds by force-closing the underlying socket,
even when the call would otherwise block indefinitely.
"""

import socket
import threading
import time
import unittest
from threading import Event

from sdt_app.transport import (
    InspectionCancelled,
    TransportOptions,
    _disconnect_fast,
    _run_interruptible,
)


class _FakeChannel:
    """Stand-in Paramiko channel whose recv blocks until the socket dies."""

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._closed = False

    def recv_ready(self) -> bool:
        return True

    def recv(self, _nbytes: int) -> bytes:
        # Blocking read: this is exactly the call we need to be able to
        # interrupt by closing the socket.
        try:
            data = self._sock.recv(_nbytes)
        except OSError:
            raise
        if not data:
            raise EOFError("connection closed")
        return data

    def settimeout(self, _t: float) -> None:
        pass


class _FakeClient:
    def __init__(self, sock: socket.socket):
        self._sock = sock

    def close(self) -> None:
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()


class InterruptibleAbortTests(unittest.TestCase):
    def test_run_interruptible_returns_value_on_success(self):
        stop = Event()
        result = _run_interruptible(
            lambda: 42,
            lambda: None,
            stop,
            poll_interval=0.05,
            join_after=0.3,
        )
        self.assertEqual(result, 42)

    def test_run_interruptible_aborts_within_bounded_time(self):
        # Open a real loopback socket pair; one end is given to the runner
        # via a fake channel/connection, the other end sits idle.  Closing
        # the socket from outside is the only way to unblock the recv.
        server, client = socket.socketpair()
        channel = _FakeChannel(server)
        connection = _FakeClient(client)
        stop = Event()

        def blocking_read():
            # This would normally block until the socket is closed.
            return channel.recv(4096)

        def on_stop():
            _disconnect_fast(connection, timeout=0.3)

        def _runner_silently_for_abort_test():
            try:
                _run_interruptible(blocking_read, on_stop, stop)
            except BaseException:
                pass

        runner_thread = threading.Thread(
            target=_runner_silently_for_abort_test,
            daemon=True,
        )
        runner_thread.start()
        time.sleep(0.1)  # let the runner enter recv()
        started = time.monotonic()
        stop.set()
        runner_thread.join(timeout=2.0)
        elapsed = time.monotonic() - started
        # The whole abort cycle should finish well under a second even
        # though the underlying recv() blocks indefinitely.
        self.assertLess(elapsed, 1.0)
        self.assertFalse(runner_thread.is_alive())
        server.close()
        client.close()

    def test_run_interruptible_raises_when_stop_already_set(self):
        stop = Event()
        stop.set()
        with self.assertRaises(InspectionCancelled):
            _run_interruptible(lambda: 1, lambda: None, stop)

    def test_run_interruptible_propagates_real_exceptions(self):
        stop = Event()

        def boom():
            raise ValueError("real failure")

        with self.assertRaises(ValueError):
            _run_interruptible(boom, lambda: None, stop)

    def test_disconnect_fast_is_time_bounded(self):
        # A close() that hangs must not block the caller beyond the
        # configured timeout.
        class Hanging:
            def close(self):
                time.sleep(5)

        started = time.monotonic()
        _disconnect_fast(Hanging(), timeout=0.2)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.5)

    def test_abort_latency_under_load(self):
        # Spawn many concurrent blocking reads and verify they all abort
        # quickly when stop_event is set.  This simulates the real
        # scenario where the user has 10+ devices being inspected at
        # once and clicks stop.
        server, client = socket.socketpair()
        channel = _FakeChannel(server)
        connection = _FakeClient(client)
        stop = Event()

        def blocking_read():
            return channel.recv(4096)

        def on_stop():
            _disconnect_fast(connection, timeout=0.3)

        def _runner_silently():
            try:
                _run_interruptible(blocking_read, on_stop, stop)
            except BaseException:
                # The runner is intentionally aborted via socket close;
                # InspectionCancelled is expected and must not be printed.
                pass

        threads = []
        for _ in range(20):
            t = threading.Thread(target=_runner_silently, daemon=True)
            t.start()
            threads.append(t)

        time.sleep(0.2)  # let all runners enter recv()
        started = time.monotonic()
        stop.set()
        for t in threads:
            t.join(timeout=2.0)
            self.assertFalse(t.is_alive())
        elapsed = time.monotonic() - started
        # 20 concurrent blocking reads should all abort within 1 second.
        self.assertLess(elapsed, 1.0)
        server.close()
        client.close()


class AbortTimingTests(unittest.TestCase):
    def test_options_have_short_abort_window(self):
        options = TransportOptions()
        # The whole stop-to-exit budget must be under one second.
        self.assertLessEqual(options.abort_join_after, 0.5)
        self.assertLessEqual(options.poll_interval, 0.1)
        self.assertLessEqual(options.recv_timeout, 0.5)


if __name__ == "__main__":
    unittest.main()
