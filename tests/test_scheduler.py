import unittest
from datetime import datetime

from sdt_app.scheduler import PeriodicScheduler


class SchedulerTests(unittest.TestCase):
    def test_daily_schedule_uses_selected_time(self):
        now = datetime(2026, 1, 1, 8, 0, 0)
        scheduler = PeriodicScheduler()
        scheduler.enable(frequency="daily", time_of_day="09:30", now=now)
        self.assertEqual(scheduler.next_run, datetime(2026, 1, 1, 9, 30))
        scheduler.mark_triggered(datetime(2026, 1, 1, 10, 0))
        self.assertEqual(scheduler.next_run, datetime(2026, 1, 2, 9, 30))

    def test_monthly_schedule_uses_selected_day(self):
        scheduler = PeriodicScheduler()
        scheduler.enable(
            frequency="monthly",
            time_of_day="09:00",
            day_of_month=15,
            now=datetime(2026, 1, 2, 8, 0),
        )
        self.assertEqual(scheduler.next_run, datetime(2026, 1, 15, 9, 0))
        scheduler.mark_triggered(datetime(2026, 1, 16, 10, 0))
        self.assertEqual(scheduler.next_run, datetime(2026, 2, 15, 9, 0))

    def test_monthly_schedule_handles_december_and_short_months(self):
        scheduler = PeriodicScheduler()
        scheduler.enable(
            frequency="monthly",
            time_of_day="23:59",
            day_of_month=31,
            now=datetime(2026, 12, 31, 23, 59),
        )
        self.assertEqual(scheduler.next_run, datetime(2027, 1, 31, 23, 59))
        scheduler.mark_triggered(datetime(2027, 2, 1, 0, 0))
        self.assertEqual(scheduler.next_run, datetime(2027, 2, 28, 23, 59))

    def test_disable_clears_schedule(self):
        scheduler = PeriodicScheduler()
        scheduler.enable(frequency="daily", time_of_day="09:00", now=datetime.now())
        scheduler.disable()
        self.assertFalse(scheduler.enabled)
        self.assertIsNone(scheduler.next_run)
        self.assertEqual(scheduler.display_next_run(), "\u672a\u542f\u7528")

    def test_invalid_frequency_time_and_day_are_rejected(self):
        scheduler = PeriodicScheduler()
        with self.assertRaises(ValueError):
            scheduler.enable(frequency="hourly", time_of_day="09:00")
        with self.assertRaises(ValueError):
            scheduler.enable(frequency="daily", time_of_day="25:00")
        with self.assertRaises(ValueError):
            scheduler.enable(frequency="monthly", time_of_day="09:00", day_of_month=32)
        with self.assertRaises(ValueError):
            scheduler.enable(frequency="weekly", time_of_day="09:00", weekday=8)

    def test_weekly_schedule_uses_selected_weekday(self):
        # 2026-01-01 is a Thursday (weekday=3).  Asking for Monday
        # (weekday=1) should land on 2026-01-05.
        now = datetime(2026, 1, 1, 8, 0, 0)
        scheduler = PeriodicScheduler()
        scheduler.enable(
            frequency="weekly", time_of_day="09:30",
            weekday=1, now=now,
        )
        self.assertEqual(scheduler.next_run, datetime(2026, 1, 5, 9, 30))
        scheduler.mark_triggered(datetime(2026, 1, 5, 10, 0))
        self.assertEqual(scheduler.next_run, datetime(2026, 1, 12, 9, 30))

    def test_weekly_schedule_handles_sunday(self):
        # 2026-01-03 is a Saturday (weekday=5).  Asking for Sunday
        # (weekday=7) should land on 2026-01-04.
        now = datetime(2026, 1, 3, 8, 0, 0)
        scheduler = PeriodicScheduler()
        scheduler.enable(
            frequency="weekly", time_of_day="06:00",
            weekday=7, now=now,
        )
        self.assertEqual(scheduler.next_run, datetime(2026, 1, 4, 6, 0))


if __name__ == "__main__":
    unittest.main()
