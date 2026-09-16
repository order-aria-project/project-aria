from __future__ import annotations

import os
import subprocess
from pathlib import Path

from core.app_registry import AppRegistry


class ApplicationLauncher:
    """Launches remembered or automatically discovered Windows applications."""

    def __init__(
        self,
        app_registry: AppRegistry,
    ) -> None:
        self.app_registry = app_registry

    @staticmethod
    def _resolve_path(
        executable: str | None,
    ) -> Path | None:
        if not executable:
            return None

        path = Path(
            os.path.expandvars(
                os.path.expanduser(
                    executable
                )
            )
        )

        if not path.is_file():
            return None

        return path

    def _launch_windows_app(
        self,
        app_id: str,
    ) -> str:
        """
        Launch a Windows Start App/AppX application.

        Example:
            explorer.exe shell:AppsFolder\<AppID>
        """

        target = (
            f"shell:AppsFolder\\{app_id}"
        )

        try:
            subprocess.Popen(
                [
                    "explorer.exe",
                    target,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )

            return (
                "STATUS=STARTED"
            )

        except OSError as exc:
            return (
                "STATUS=FAILED "
                f"Windows failed to launch "
                f"Windows application: {exc}"
            )

        except Exception as exc:
            return (
                "STATUS=FAILED "
                f"Unexpected error launching "
                f"Windows application: {exc}"
            )

    def _launch_executable(
        self,
        executable_path: Path,
        app_name: str,
    ) -> str:
        try:
            startupinfo = (
                subprocess.STARTUPINFO()
            )

            startupinfo.dwFlags |= (
                subprocess.STARTF_USESHOWWINDOW
            )

            startupinfo.wShowWindow = (
                subprocess.SW_HIDE
            )

            subprocess.Popen(
                [
                    str(
                        executable_path
                    )
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                ),
                close_fds=True,
            )

            return (
                "STATUS=STARTED "
                f"'{app_name}' "
                "was launched successfully."
            )

        except FileNotFoundError:
            return (
                "STATUS=NOT_FOUND "
                f"Windows could not find: "
                f"{executable_path}"
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

    def launch(
        self,
        app_name: str,
    ) -> str:
        app_name = app_name.strip()

        if not app_name:
            return (
                "STATUS=NOT_FOUND "
                "No application name was provided."
            )

        # --------------------------------------------------------------
        # 1. Existing registry entry.
        # --------------------------------------------------------------

        application = (
            self.app_registry.get_application(
                app_name
            )
        )

        discovered = False

        if application:
            application_type = (
                application.get(
                    "type",
                    "exe",
                )
            )

            # ----------------------------------------------------------
            # Windows Start App
            # ----------------------------------------------------------

            if (
                application_type
                == "windows_app"
            ):
                app_id = application.get(
                    "app_id"
                )

                if app_id:
                    result = (
                        self._launch_windows_app(
                            app_id
                        )
                    )

                    if result.startswith(
                        "STATUS=STARTED"
                    ):
                        return (
                            "STATUS=STARTED "
                            f"'{app_name}' "
                            "was launched successfully."
                        )

            # ----------------------------------------------------------
            # Normal executable
            # ----------------------------------------------------------

            else:
                executable = application.get(
                    "executable"
                )

                executable_path = (
                    self._resolve_path(
                        executable
                    )
                )

                if executable_path:
                    return (
                        self._launch_executable(
                            executable_path,
                            app_name,
                        )
                    )

        # --------------------------------------------------------------
        # 2. Registry entry missing or stale.
        #    Search Windows.
        # --------------------------------------------------------------

        print(
            f"[APP] '{app_name}' "
            "is not currently available. "
            "Searching Windows..."
        )

        discovered_target = (
            self.app_registry
            .discover_and_register(
                app_name
            )
        )

        if not discovered_target:
            return (
                "STATUS=NOT_FOUND "
                f"Application '{app_name}' "
                "could not be found on this computer."
            )

        discovered = True

        # --------------------------------------------------------------
        # 3. Determine what Windows discovery returned.
        # --------------------------------------------------------------

        refreshed = (
            self.app_registry.get_application(
                app_name
            )
        )

        if not refreshed:
            return (
                "STATUS=UNKNOWN "
                f"Application '{app_name}' "
                "was discovered but could not "
                "be loaded from the registry."
            )

        application_type = (
            refreshed.get(
                "type",
                "exe",
            )
        )

        # --------------------------------------------------------------
        # 4. Windows Start App.
        # --------------------------------------------------------------

        if (
            application_type
            == "windows_app"
        ):
            app_id = refreshed.get(
                "app_id"
            )

            if not app_id:
                return (
                    "STATUS=UNKNOWN "
                    f"Windows found '{app_name}', "
                    "but no App ID was available."
                )

            result = (
                self._launch_windows_app(
                    app_id
                )
            )

            if result.startswith(
                "STATUS=STARTED"
            ):
                print(
                    f"[APP] Found '{app_name}' "
                    f"as Windows Start App: "
                    f"{app_id}"
                )

                return (
                    "STATUS=STARTED "
                    f"'{app_name}' was found, "
                    "remembered, and launched "
                    "successfully."
                )

            return result

        # --------------------------------------------------------------
        # 5. Normal executable.
        # --------------------------------------------------------------

        executable = refreshed.get(
            "executable"
        )

        executable_path = (
            self._resolve_path(
                executable
            )
        )

        if not executable_path:
            return (
                "STATUS=NOT_FOUND "
                f"Application '{app_name}' "
                "was discovered, but its "
                "executable is no longer available."
            )

        print(
            f"[APP] Found '{app_name}': "
            f"{executable_path}"
        )

        result = self._launch_executable(
            executable_path,
            app_name,
        )

        if result.startswith(
            "STATUS=STARTED"
        ):
            return (
                "STATUS=STARTED "
                f"'{app_name}' was found, "
                "remembered, and launched "
                "successfully."
            )

        return result

    def open(
        self,
        app_name: str,
    ) -> str:
        return self.launch(
            app_name
        )