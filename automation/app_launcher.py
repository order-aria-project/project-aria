from pathlib import Path
import subprocess

from core.app_registry import AppRegistry


class ApplicationLauncher:
    """Launches applications registered with ARIA."""

    def __init__(self, registry: AppRegistry) -> None:
        self.registry = registry

    def launch(self, app_name: str) -> str:
        """Launch a registered application."""
        executable = self.registry.get(app_name)

        if not executable:
            return f"I don't know where {app_name} is installed."

        executable_path = Path(executable)

        if not executable_path.exists():
            return (
                f"I found {app_name}, but its executable no longer exists "
                f"at {executable_path}."
            )

        try:
            subprocess.Popen(
            [str(executable_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )

            return f"Opening {app_name}."

        except OSError as exc:
            return f"I couldn't open {app_name}: {exc}"