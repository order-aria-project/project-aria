from __future__ import annotations

import os
import subprocess
from pathlib import Path

from core.app_registry import AppRegistry


class ApplicationCloser:
    """
    Closes Windows applications without opening visible Windows UI.

    ARIA uses taskkill.exe directly for normal executables.
    Windows Start/AppX applications use a hidden PowerShell fallback.

    ARIA never targets itself or core Windows shell processes.
    """

    PROTECTED_NAMES = {
        "aria",
        "a.r.i.a",
        "python",
        "python3",
        "powershell",
        "pwsh",
        "cmd",
        "explorer",
        "system",
        "taskmgr",
        "task manager",
    }

    def __init__(
        self,
        app_registry: AppRegistry,
    ) -> None:
        self.app_registry = app_registry

    @staticmethod
    def _normalise(
        value: str,
    ) -> str:
        return (
            value.lower()
            .strip()
            .replace(".exe", "")
        )

    @staticmethod
    def _hidden_creation_flags() -> int:
        return getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0,
        )

    def _taskkill_image(
        self,
        executable_name: str,
    ) -> tuple[bool, str]:
        """
        Terminate an executable directly.

        This does not open Task Manager or any console window.
        """
        try:
            result = subprocess.run(
                [
                    "taskkill.exe",
                    "/F",
                    "/T",
                    "/IM",
                    executable_name,
                ],
                capture_output=True,
                text=True,
                creationflags=self._hidden_creation_flags(),
                stdin=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )

        except FileNotFoundError:
            return (
                False,
                "taskkill.exe was not found.",
            )

        except Exception as exc:
            return (
                False,
                f"Could not run taskkill: {exc}",
            )

        output = (
            result.stdout
            + "\n"
            + result.stderr
        ).strip()

        upper = output.upper()

        if (
            "SUCCESS" in upper
            or "TERMINATED" in upper
        ):
            return (
                True,
                output,
            )

        if (
            "NOT FOUND" in upper
            or "NO RUNNING INSTANCE" in upper
            or "COULD NOT BE FOUND" in upper
        ):
            return (
                False,
                output,
            )

        return (
            False,
            output,
        )

    def _close_by_window_title(
        self,
        app_name: str,
    ) -> int:
        """
        Hidden fallback for Windows Start/AppX applications.

        No visible PowerShell or Task Manager window is created.
        """
        script = r"""
param(
    [string]$Target
)

$ErrorActionPreference = "SilentlyContinue"

$targetText = $Target.Trim().ToLower()

if ([string]::IsNullOrWhiteSpace($targetText)) {
    Write-Output "0"
    exit 0
}

$processes = Get-Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.MainWindowTitle -and
        $_.MainWindowTitle.ToLower().Contains($targetText)
    }

$count = 0

foreach ($process in $processes) {
    try {
        Stop-Process `
            -Id $process.Id `
            -Force `
            -ErrorAction Stop

        $count++
    }
    catch {
    }
}

Write-Output $count
"""

        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    script,
                    "-Target",
                    app_name,
                ],
                capture_output=True,
                text=True,
                creationflags=self._hidden_creation_flags(),
                stdin=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )

            try:
                return int(
                    result.stdout.strip()
                    or "0"
                )
            except ValueError:
                return 0

        except Exception:
            return 0

    def close(
        self,
        app_name: str,
    ) -> str:
        requested = app_name.strip()

        if not requested:
            return (
                "STATUS=NOT_FOUND "
                "No application name was provided."
            )

        normalised_requested = (
            self._normalise(requested)
        )

        if (
            normalised_requested
            in self.PROTECTED_NAMES
        ):
            return (
                "STATUS=FAILED "
                f"ARIA will not close "
                f"'{requested}'."
            )

        application = (
            self.app_registry.get_application(
                requested
            )
        )

        if not application:
            self.app_registry.discover_and_register(
                requested
            )

            application = (
                self.app_registry.get_application(
                    requested
                )
            )

        if not application:
            return (
                "STATUS=NOT_FOUND "
                f"Application '{requested}' "
                "could not be found."
            )

        application_type = (
            application.get(
                "type",
                "exe",
            )
        )

        # ------------------------------------------------------------
        # Normal executable
        # ------------------------------------------------------------

        if application_type == "exe":
            executable = application.get(
                "executable"
            )

            if executable:
                executable_path = Path(
                    os.path.expandvars(
                        os.path.expanduser(
                            executable
                        )
                    )
                )

                image_name = (
                    executable_path.name
                )

                if image_name:
                    closed, output = (
                        self._taskkill_image(
                            image_name
                        )
                    )

                    if closed:
                        return (
                            "STATUS=STARTED "
                            f"'{requested}' "
                            "was closed."
                        )

                    upper = output.upper()

                    if (
                        "NOT FOUND" in upper
                        or "NO RUNNING INSTANCE"
                        in upper
                        or "COULD NOT BE FOUND"
                        in upper
                    ):
                        return (
                            "STATUS=NOT_FOUND "
                            f"'{requested}' is not "
                            "currently running."
                        )

                    return (
                        "STATUS=FAILED "
                        f"Could not close "
                        f"'{requested}': "
                        f"{output}"
                    )

        # ------------------------------------------------------------
        # Windows Start App / AppX fallback
        # ------------------------------------------------------------

        count = (
            self._close_by_window_title(
                requested
            )
        )

        if count > 0:
            return (
                "STATUS=STARTED "
                f"'{requested}' was closed."
            )

        return (
            "STATUS=NOT_FOUND "
            f"'{requested}' is not "
            "currently running."
        )