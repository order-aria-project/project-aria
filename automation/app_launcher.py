from pathlib import Path
import subprocess
import time

import psutil

from core.app_registry import AppRegistry


class ApplicationLauncher:
    """Launches applications registered with ARIA."""

    def __init__(self, registry: AppRegistry) -> None:
        self.registry = registry

    def launch(
        self,
        app_name: str,
        verify: bool = True,
    ) -> str:
        """
        Launch a registered application and optionally verify it started.

        Args:
            app_name: Registered application name.
            verify: Whether to verify the process started.

        Returns:
            A detailed result describing what happened.
        """

        executable = self.registry.get(app_name)

        if not executable:
            return (
                f"STATUS=NOT_FOUND; "
                f"message=I don't know where {app_name} is installed."
            )

        executable_path = Path(executable)

        if not executable_path.exists():
            return (
                f"STATUS=NOT_FOUND; "
                f"message=The registered executable for {app_name} "
                f"does not exist at {executable_path}."
            )

        try:
            process = subprocess.Popen(
                [str(executable_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )

        except OSError as exc:
            return (
                f"STATUS=FAILED; "
                f"message=Windows could not start {app_name}: {exc}"
            )

        if not verify:
            return (
                f"STATUS=STARTED; "
                f"message={app_name} launch command was accepted."
            )

        # Give the application a moment to create its process.
        time.sleep(1.0)

        # First check the process ID we got from Windows.
        if process.poll() is None:
            return (
                f"STATUS=RUNNING; "
                f"message={app_name} started successfully; "
                f"pid={process.pid}."
            )

        # Fallback: search by executable name.
        executable_name = executable_path.name.lower()

        for candidate in psutil.process_iter(["name", "exe"]):
            try:
                process_name = (
                    candidate.info.get("name") or ""
                ).lower()

                process_exe = (
                    candidate.info.get("exe") or ""
                ).lower()

                if (
                    process_name == executable_name
                    or process_exe == str(executable_path).lower()
                ):
                    return (
                        f"STATUS=RUNNING; "
                        f"message={app_name} is running."
                    )

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
            ):
                continue

        return (
            f"STATUS=UNKNOWN; "
            f"message=The launch request for {app_name} "
            f"was accepted, but I could not confirm that "
            f"the application is still running."
        )