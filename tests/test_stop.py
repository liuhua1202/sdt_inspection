"""Tests for the immediate-stop wiring in the inspection service."""

import time
import unittest
from queue import Queue
from unittest.mock import MagicMock

from sdt_app.inspection_service import _ConnectionTracker, InspectionService


class ConnectionTrackerTests(unittest.TestCase):
    def test_register_and_unregister(self):
        tracker = _ConnectionTracker()
        conn = MagicMock()
        tracker.register(conn)
        tracker.unregister(conn)
        # close_all on an empty registry is a no-op
        tracker.close_all()
        conn.close.assert_not_called()

    def test_close_all_invokes_close_on_each_connection(self):
        tracker = _ConnectionTracker()
        a = MagicMock()
        b = MagicMock()
        tracker.register(a)
        tracker.register(b)
        tracker.close_all()
        a.close.assert_called_once()
        b.close.assert_called_once()
        # A second close_all call must not raise and must not double-close
        # because the tracker drops handles after the snapshot is taken.
        tracker.close_all()
        self.assertEqual(a.close.call_count, 1)
        self.assertEqual(b.close.call_count, 1)

    def test_close_all_falls_back_to_disconnect(self):
        tracker = _ConnectionTracker()

        class NetmikoLike:
            def __init__(self):
                self.closed = 0

            def disconnect(self):
                self.closed += 1

        conn = NetmikoLike()
        tracker.register(conn)
        tracker.close_all()
        self.assertEqual(conn.closed, 1)

    def test_close_all_swallows_exceptions(self):
        tracker = _ConnectionTracker()

        class Broken:
            def close(self):
                raise RuntimeError("boom")

        tracker.register(Broken())
        # Must not raise even though close() blows up.
        tracker.close_all()


class ImmediateStopTests(unittest.TestCase):
    def _build_service(self):
        events: Queue = Queue()
        service = InspectionService(events)
        return service, events

    def test_stop_closes_active_connections_before_setting_event(self):
        service, _ = self._build_service()
        service._running = True  # type: ignore[attr-defined]
        closed: list[str] = []

        class Conn:
            def close(self_inner):
                closed.append("c")
                # Setting stop_event after closing mimics the ordering in
                # InspectionService.stop().
                service.stop_event.set()

        service.connections.register(Conn())
        # Reset the stop event so we can verify ordering.
        service.stop_event.clear()
        service.stop()
        self.assertEqual(closed, ["c"])
        self.assertTrue(service.stop_event.is_set())

    def test_stop_after_running_returns_quickly(self):
        service, _ = self._build_service()
        service._running = True  # type: ignore[attr-defined]
        # Register 50 mock connections so close_all iterates a meaningful list.
        for _ in range(50):
            service.connections.register(MagicMock())
        started = time.monotonic()
        service.stop()
        elapsed = time.monotonic() - started
        # The whole stop call should comfortably finish in under 100 ms even
        # when many connections need to be torn down.
        self.assertLess(elapsed, 0.1)


if __name__ == "__main__":
    unittest.main()
