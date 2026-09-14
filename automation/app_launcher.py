from __future__ import annotations

import os
import subprocess
from pathlib import Path

from core.app_registry import AppRegistry


class ApplicationLauncher:
    """Launches registered Windows applications."""

    def __init__(self, app_registry: AppRegistry) -> None:
        self.app_registry = app_registry

    def launch(self, app_name: str) -> str:
        executable = self.app_registry.get(app_name)

        if not executable:
            return (
                "STATUS=NOT_FOUND "
                f"Application '{app_name}' is not registered."
            )

        executable_path = Path(
            os.path.expandvars(
                os.path.expanduser(executable)
            )
        )

        if not executable_path.exists():
            return (
                "STATUS=NOT_FOUND "
                f"Executable does not exist: {executable_path}"
            )

        if not executable_path.is_file():
            return (
                "STATUS=NOT_FOUND "
                f"Executable path is not a file: {executable_path}"
            )

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            subprocess.Popen(
                [str(executable_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )

        except FileNotFoundError:
            return (
                "STATUS=NOT_FOUND "
                f"Windows could not find: {executable_path}"
            )

        except OSError as exc:
            return (
                "STATUS=FAILED "
                f"Windows failed to launch "
                f"'{app_name}': {exc}"
            )

        except Exception as exc:
            return (
                "STATUS=FAILED "
                f"Unexpected error launching "
                f"'{app_name}': {exc}"
            )

        return (
            "STATUS=STARTED "
            f"'{app_name}' was launched successfully."
        )

    def open(self, app_name: str) -> str:
        return self.launch(app_name)