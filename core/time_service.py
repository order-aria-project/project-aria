from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimeService:
    """Local clock/date service for ARIA.

    Standalone by design so it can be tested before being wired into ARIA's
    existing tool router. It uses the Windows/Linux system clock unless a
    timezone is explicitly supplied.
    """

    def __init__(self, timezone_name: str | None = None) -> None:
        self.timezone_name = timezone_name
        self._zone = self._load_zone(timezone_name)

    @staticmethod
    def _load_zone(timezone_name: str | None):
        if not timezone_name:
            return None
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"Unknown IANA timezone: {timezone_name}"
            ) from exc

    def now(self) -> datetime:
        return datetime.now(tz=self._zone)

    def snapshot(self) -> dict[str, str]:
        current = self.now()
        return {
            "iso": current.isoformat(),
            "date": current.strftime("%A, %d %B %Y"),
            "time": current.strftime("%H:%M:%S"),
            "day": current.strftime("%A"),
            "month": current.strftime("%B"),
            "year": current.strftime("%Y"),
            "timezone": (
                current.tzname() or "local"
            ),
        }

    def format_human(self) -> str:
        current = self.now()
        return current.strftime(
            "%A, %d %B %Y at %H:%M:%S"
        )

    def add(self, **kwargs: int) -> dict[str, str]:
        current = self.now() + timedelta(**kwargs)
        return {
            "iso": current.isoformat(),
            "date": current.strftime("%A, %d %B %Y"),
            "time": current.strftime("%H:%M:%S"),
            "timezone": current.tzname() or "local",
        }
