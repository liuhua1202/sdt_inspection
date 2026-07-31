"""Calendar-based periodic task scheduler used by the Tk UI."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta


FREQUENCIES = {"daily", "weekly", "monthly"}


@dataclass
class PeriodicScheduler:
    """Calculate daily / weekly / monthly execution times without a worker thread."""

    enabled: bool = False
    frequency: str = "daily"
    time_of_day: str = "09:00"
    day_of_month: int = 1
    weekday: int = 1  # 1 = Monday ... 7 = Sunday
    next_run: datetime | None = None

    @staticmethod
    def _parse_time(time_of_day: str) -> tuple[int, int]:
        try:
            hour_text, minute_text = time_of_day.strip().split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        except (AttributeError, ValueError) as exc:
            raise ValueError("\u65f6\u95f4\u5fc5\u987b\u4f7f\u7528 HH:MM \u683c\u5f0f") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("\u65f6\u95f4\u5fc5\u987b\u5728 00:00 \u5230 23:59 \u4e4b\u95f4")
        return hour, minute

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        return calendar.monthrange(year, month)[1]

    @staticmethod
    def _next_month(year: int, month: int) -> tuple[int, int]:
        if month == 12:
            return year + 1, 1
        return year, month + 1

    def _calculate_next(self, now: datetime) -> datetime:
        hour, minute = self._parse_time(self.time_of_day)
        if self.frequency == "daily":
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate
        if self.frequency == "weekly":
            # weekday is 1..7 (Mon..Sun); datetime.weekday() is 0..6
            target_weekday = (self.weekday - 1) % 7
            days_ahead = target_weekday - now.weekday()
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if days_ahead < 0 or (days_ahead == 0 and candidate <= now):
                days_ahead += 7
            candidate = candidate + timedelta(days=days_ahead)
            return candidate
        if self.frequency == "monthly":
            day = min(self.day_of_month, self._days_in_month(now.year, now.month))
            candidate = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                year, month = self._next_month(now.year, now.month)
                day = min(self.day_of_month, self._days_in_month(year, month))
                candidate = candidate.replace(year=year, month=month, day=day)
            return candidate
        raise ValueError("\u8ba1\u5212\u5468\u671f\u5fc5\u987b\u662f daily / weekly / monthly")

    def enable(
        self,
        frequency: str = "daily",
        time_of_day: str = "09:00",
        day_of_month: int = 1,
        weekday: int = 1,
        now: datetime | None = None,
    ) -> None:
        if frequency not in FREQUENCIES:
            raise ValueError("\u8ba1\u5212\u5468\u671f\u5fc5\u987b\u662f\u6bcf\u5929 / \u6bcf\u5468 / \u6bcf\u6708")
        if not 1 <= day_of_month <= 31:
            raise ValueError("\u6bcf\u6708\u65e5\u671f\u5fc5\u987b\u5728 1 \u5230 31 \u4e4b\u95f4")
        if not 1 <= weekday <= 7:
            raise ValueError("\u6bcf\u5468\u5468\u51e0\u5fc5\u987b\u5728 1 \u5230 7 \u4e4b\u95f4")
        self._parse_time(time_of_day)
        self.frequency = frequency
        self.time_of_day = time_of_day
        self.day_of_month = day_of_month
        self.weekday = weekday
        self.enabled = True
        self.next_run = self._calculate_next(now or datetime.now())

    def disable(self) -> None:
        self.enabled = False
        self.next_run = None

    def is_due(self, now: datetime | None = None) -> bool:
        return bool(self.enabled and self.next_run and (now or datetime.now()) >= self.next_run)

    def mark_triggered(self, now: datetime | None = None) -> None:
        if self.enabled:
            self.next_run = self._calculate_next(now or datetime.now())

    def display_next_run(self) -> str:
        if not self.enabled or self.next_run is None:
            return "\u672a\u542f\u7528"
        return self.next_run.strftime("%Y-%m-%d %H:%M:%S")
