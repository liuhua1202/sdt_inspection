"""Regression tests for the daemon-thread ``close_all`` fix (P1-A).

The previous implementation called ``connection.close()`` synchronously
on the caller thread.  On Windows, a ``net_connect.disconnect()`` on a
half-dead socket can block for the full TCP shutdown timeout (often
5+ seconds), which made the Stop button feel frozen.

The fix wraps each ``close()`` in a daemon thread with a per-connection
timeout.  These tests verify that:

  1. ``close_all`` returns within a bounded time even when one
     connection's close() hangs forever.
  2. A subsequent ``close_all`` is a no-op (the tracker cleared the
     list).
  3. Connections that close quickly still get their ``close()`` /
     ``disconnect()`` called.
"""
import time
import unittest
from unittest.mock import MagicMock

from sdt_app.inspection_service import _ConnectionTracker


class HangingCloseTimeoutTests(unittest.TestCase):
    def test_hanging_close_does_not_block_close_all(self):
        class Hanging:
            def close(self):
                time.sleep(5)

        tracker = _ConnectionTracker()
        tracker.register(Hanging())
        started = time.monotonic()
        tracker.close_all()
        elapsed = time.monotonic() - started
        # The per-connection CLOSE_TIMEOUT is 0.5s; a single
        # hanging close must not run past a second in total.
        self.assertLess(elapsed, 1.0)

    def test_normal_close_still_invoked(self):
        conn = MagicMock()
        tracker = _ConnectionTracker()
        tracker.register(conn)
        tracker.close_all()
        conn.close.assert_called_once()

    def test_close_all_is_idempotent(self):
        conn = MagicMock()
        tracker = _ConnectionTracker()
        tracker.register(conn)
        tracker.close_all()
        tracker.close_all()
        # MagicMock records every call; we expect exactly one.
        self.assertEqual(conn.close.call_count, 1)


if __name__ == "__main__":
    unittest.main()
