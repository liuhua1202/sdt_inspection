"""Tests for the transport-layer read loops to make sure stop events are honored promptly."""

import time
import unittest
from threading import Event
from unittest.mock import MagicMock

from sdt_app.transport import (
    InspectionCancelled,
    TransportOptions,
    _read_paramiko,
)


class _FakeChannel:
    """Minimal stand-in for a Paramiko channel that the read loop can drive."""

    def __init__(self, ready=False, payload=b"", error=None):
        self._ready = ready
        self._payload = payload
        self._error = error
        self.recv_calls = 0
        self.ready_calls = 0
        self.closed = False

    def recv_ready(self):
        self.ready_calls += 1
        if self._error is not None:
            raise self._error
        return self._ready

    def recv(self, _nbytes):
        self.recv_calls += 1
        if self._error is not None:
            raise self._error
        return self._payload


class ReadLoopStopTests(unittest.TestCase):
    def test_paramiko_read_returns_immediately_when_stop_set(self):
        # Channel that never produces data: the worker is "stuck" waiting for
        # the remote device.  Setting stop_event must short-circuit the loop
        # in well under a second instead of waiting for the 15s read timeout.
        channel = _FakeChannel(ready=False, payload=b"")
        options = TransportOptions(read_timeout=15.0, recv_timeout=1.0, poll_interval=0.05)
        stop_event = Event()
        stop_event.set()

        started = time.monotonic()
        with self.assertRaises(InspectionCancelled):
            _read_paramiko(channel, options, stop_event)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.5)
        # The loop must not have polled the channel a single time when stop is
        # already set before the read began.
        self.assertEqual(channel.ready_calls, 0)

    def test_paramiko_read_shortens_quiet_wait_when_stop_set(self):
        # Channel delivers one chunk of data and then goes silent.  Once stop
        # is set, the quiet-wait window collapses from 0.8s to ~0.05s so the
        # worker exits almost immediately instead of waiting for the prompt.
        channel = _FakeChannel(ready=True, payload=b"some output\n")
        options = TransportOptions(read_timeout=15.0, recv_timeout=0.1, poll_interval=0.05, quiet_timeout=0.8)
        stop_event = Event()

        def set_stop_after_first_chunk():
            time.sleep(0.05)
            stop_event.set()

        import threading
        threading.Thread(target=set_stop_after_first_chunk, daemon=True).start()
        started = time.monotonic()
        with self.assertRaises(InspectionCancelled):
            _read_paramiko(channel, options, stop_event)
        elapsed = time.monotonic() - started
        # Must finish well before the full quiet_timeout of 0.8s.
        self.assertLess(elapsed, 0.6)

    def test_paramiko_read_treats_eof_as_cancellation_when_stop_set(self):
        # Channel raises EOFError mid-read because the socket was closed by
        # _ConnectionTracker.close_all().  The reader must translate this into
        # an InspectionCancelled so the worker exits cleanly.
        channel = _FakeChannel(ready=True, error=EOFError("connection closed"))
        options = TransportOptions(read_timeout=15.0, recv_timeout=0.1, poll_interval=0.05)
        stop_event = Event()
        stop_event.set()

        with self.assertRaises(InspectionCancelled):
            _read_paramiko(channel, options, stop_event)


if __name__ == "__main__":
    unittest.main()
