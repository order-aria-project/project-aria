from __future__ import annotations

import os
import subprocess
import sys


TASK_NAME = "ARIA-Elevated"
PROJECT_NAME = "A:\\Core\\Project"


def _is_aria_main() -> bool:
    if not sys.argv:
        return False

    try:
        script = os.path.abspath(sys.argv[0])
    except Exception:
        return False

    return (
        os.path.basename(script).lower()
        == "main.py"
        and os.path.abspath(os.getcwd()).lower()
        == PROJECT_NAME.lower()
    )


def _is_administrator() -> bool:
    try:
        import ctypes

        return bool(
            ctypes.windll.shell32.IsUserAnAdmin()
        )
    except Exception:
        return False


def _aria_task_is_running() -> bool:
    try:
        result = subprocess.run(
            [
                "schtasks.exe",
                "/Query",
                "/TN",
                TASK_NAME,
                "/FO",
                "CSV",
                "/NH",
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=5,
        )

        if result.returncode != 0:
            return False

        return "RUNNING" in result.stdout.upper()

    except Exception:
        return False


def _start_elevated_aria() -> bool:
    try:
        result = subprocess.run(
            [
                "schtasks.exe",
                "/Run",
                "/TN",
                TASK_NAME,
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )

        return result.returncode == 0

    except Exception:
        return False


if _is_aria_main() and not _is_administrator():

    if not _aria_task_is_running():
        _start_elevated_aria()

    # Prevent the non-elevated copy of ARIA from continuing.
    raise SystemExit(0)