from __future__ import annotations

from core.time_service import TimeService

_TIME_SERVICE = TimeService("Europe/London")

def _spoken_clock(dt) -> str:
    hour = dt.strftime("%I").lstrip("0") or "0"
    return f"{hour}:{dt.strftime('%M')} {dt.strftime('%p')}"

def get_current_time() -> str:
    return _spoken_clock(_TIME_SERVICE.now())

def get_current_date() -> str:
    return _TIME_SERVICE.now().strftime("%A, %B %d, %Y")

def get_current_datetime() -> str:
    dt = _TIME_SERVICE.now()
    return f"{dt.strftime('%A, %B %d, %Y')} at {_spoken_clock(dt)}"
