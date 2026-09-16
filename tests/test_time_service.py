from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.time_service import TimeService


def main() -> None:
    service = TimeService()

    current = service.now()
    assert isinstance(current, datetime)

    snapshot = service.snapshot()
    required = {
        "iso",
        "date",
        "time",
        "day",
        "month",
        "year",
        "timezone",
    }
    assert required.issubset(snapshot)
    assert len(snapshot["date"]) > 0
    assert len(snapshot["time"]) > 0

    future = service.add(minutes=5)
    assert future["iso"] != snapshot["iso"]

    london = TimeService("Europe/London")
    london_snapshot = london.snapshot()
    assert london_snapshot["timezone"] in {"GMT", "BST"}

    print("PASS local clock")
    print("PASS structured snapshot")
    print("PASS relative time")
    print("PASS Europe/London timezone")
    print("TimeService regression: 4/4 passed")


if __name__ == "__main__":
    main()
