from core.app_registry import AppRegistry
from automation.app_launcher import ApplicationLauncher


class ApplicationTools:
    """Safe application-control tools exposed to ARIA."""

    def __init__(self, registry: AppRegistry) -> None:
        self.launcher = ApplicationLauncher(registry)

    def launch(self, app_name: str) -> str:
        """
        Launch a registered application.

        The launcher returns the authoritative launch status.
        ARIA should not perform a second verification step because
        applications such as Blender may take time to initialize
        or temporarily appear unresponsive during startup.
        """
        return self.launcher.launch(app_name)