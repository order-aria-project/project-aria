from __future__ import annotations

from core.app_registry import AppRegistry
from automation.app_launcher import ApplicationLauncher
from automation.app_closer import ApplicationCloser


class ApplicationTools:
    """
    Safe application-control tools exposed to ARIA.
    """

    def __init__(
        self,
        registry: AppRegistry,
    ) -> None:
        self.launcher = ApplicationLauncher(
            registry
        )

        self.closer = ApplicationCloser(
            registry
        )

    def launch(
        self,
        app_name: str,
    ) -> str:
        """
        Launch an application.

        The launcher handles remembered applications,
        Windows discovery, and authoritative status.
        """
        return self.launcher.launch(
            app_name
        )

    def open(
        self,
        app_name: str,
    ) -> str:
        """Alias for launch()."""
        return self.launch(
            app_name
        )

    def close(
        self,
        app_name: str,
    ) -> str:
        """
        Close an application without opening
        Task Manager or another visible helper UI.
        """
        return self.closer.close(
            app_name
        )