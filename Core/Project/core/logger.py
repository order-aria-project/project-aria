from datetime import datetime
from pathlib import Path
import json
from typing import Any


class ARIALogger:
    """
    Central logging system for ARIA.

    Writes both:
    1. A human-readable Mission Log.
    2. A structured JSONL Trust Ledger.
    """

    def __init__(
        self,
        mission_log_path: Path,
        trust_ledger_path: Path,
    ) -> None:
        self.mission_log_path = mission_log_path
        self.trust_ledger_path = trust_ledger_path

        self.mission_log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.trust_ledger_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _timestamp(self) -> str:
        """Return the current local timestamp."""
        return datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def log(
        self,
        event_type: str,
        message: str,
        **details: Any,
    ) -> None:
        """
        Write an event immediately to both logs.

        Args:
            event_type: Type of event.
            message: Human-readable description.
            details: Additional structured information.
        """

        timestamp = self._timestamp()

        # -------------------------
        # Human-readable log
        # -------------------------

        mission_line = (
            f"[{timestamp}] "
            f"[{event_type.upper()}] "
            f"{message}\n"
        )

        with self.mission_log_path.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(mission_line)
            file.flush()

        # -------------------------
        # Structured Trust Ledger
        # -------------------------

        ledger_entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "message": message,
            "details": details,
        }

        with self.trust_ledger_path.open(
            "a",
            encoding="utf-8",
        ) as file:
            json.dump(
                ledger_entry,
                file,
                ensure_ascii=False,
            )
            file.write("\n")
            file.flush()