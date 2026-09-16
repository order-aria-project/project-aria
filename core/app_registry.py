from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


class AppRegistry:
    """
    Persistent application registry and Windows application discovery.

    ARIA understands both:
        - traditional .exe applications
        - Windows Start Apps / AppX applications

    A remembered application can therefore point to either:
        an executable path
        or a Windows AppsFolder application ID.
    """

    DISCOVERY_ROOTS = [
        Path(
            os.environ.get(
                "ProgramFiles",
                r"C:\Program Files",
            )
        ),
        Path(
            os.environ.get(
                "ProgramFiles(x86)",
                r"C:\Program Files (x86)",
            )
        ),
        Path(
            os.environ.get(
                "LOCALAPPDATA",
                "",
            )
        ),
        Path(
            os.environ.get(
                "APPDATA",
                "",
            )
        ),
    ]

    EXECUTABLE_HINTS = {
        "blender": [
            "blender.exe",
        ],
        "brave": [
            "brave.exe",
        ],
        "brave browser": [
            "brave.exe",
        ],
        "chrome": [
            "chrome.exe",
        ],
        "google chrome": [
            "chrome.exe",
        ],
        "discord": [
            "discord.exe",
        ],
        "discord app": [
            "discord.exe",
        ],
        "spotify": [
            "spotify.exe",
        ],
        "spotify music": [
            "spotify.exe",
        ],
        "obs": [
            "obs64.exe",
            "obs.exe",
        ],
        "obs studio": [
            "obs64.exe",
            "obs.exe",
        ],
        "firefox": [
            "firefox.exe",
        ],
        "edge": [
            "msedge.exe",
        ],
        "microsoft edge": [
            "msedge.exe",
        ],
        "steam": [
            "steam.exe",
        ],
        "roblox": [
            "RobloxPlayerBeta.exe",
            "Roblox.exe",
        ],
        "roblox player": [
            "RobloxPlayerBeta.exe",
            "Roblox.exe",
        ],
        "roblox studio": [
            "RobloxStudioBeta.exe",
        ],
    }

    GENERIC_WORDS = {
        "app",
        "application",
        "program",
        "software",
        "launcher",
        "browser",
        "player",
        "studio",
        "tool",
    }

    def __init__(
        self,
        registry_path: Path,
    ) -> None:
        self.registry_path = registry_path

        self.registry_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.registry_path.exists():
            self._save(
                {
                    "applications": {}
                }
            )

    # ------------------------------------------------------------------
    # Name handling
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_name(
        name: str,
    ) -> str:
        value = name.strip().lower()

        if value.endswith(".exe"):
            value = value[:-4]

        value = re.sub(
            r"[^a-z0-9]+",
            " ",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

        return value

    @classmethod
    def _comparison_name(
        cls,
        name: str,
    ) -> str:
        words = cls._normalise_name(
            name
        ).split()

        filtered = [
            word
            for word in words
            if word not in cls.GENERIC_WORDS
        ]

        return " ".join(filtered)

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        try:
            with self.registry_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

        except (
            json.JSONDecodeError,
            FileNotFoundError,
        ):
            return {
                "applications": {}
            }

        if "applications" not in data:
            upgraded = {
                "applications": {}
            }

            for name, executable in data.items():
                if not isinstance(
                    executable,
                    str,
                ):
                    continue

                canonical = self._normalise_name(
                    Path(executable).stem
                )

                upgraded[
                    "applications"
                ][canonical] = {
                    "type": "exe",
                    "executable": executable,
                    "aliases": [
                        self._normalise_name(
                            name
                        ),
                        canonical,
                    ],
                }

            return upgraded

        # Upgrade older remembered entries that lack "type".
        applications = data.get(
            "applications",
            {},
        )

        for canonical, details in applications.items():
            if "type" not in details:
                if details.get(
                    "app_id"
                ):
                    details["type"] = "windows_app"
                else:
                    details["type"] = "exe"

        return data

    def _save(
        self,
        data: dict,
    ) -> None:
        with self.registry_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                indent=4,
            )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        executable: str,
        aliases: list[str] | None = None,
    ) -> None:
        self.register_exe(
            name=name,
            executable=executable,
            aliases=aliases,
        )

    def register_exe(
        self,
        name: str,
        executable: str,
        aliases: list[str] | None = None,
    ) -> None:
        data = self._load()

        canonical = self._normalise_name(
            name
        )

        application = data[
            "applications"
        ].get(
            canonical,
            {
                "type": "exe",
                "executable": executable,
                "aliases": [],
            },
        )

        application["type"] = "exe"
        application["executable"] = executable

        aliases_set = set(
            application.get(
                "aliases",
                [],
            )
        )

        aliases_set.add(
            canonical
        )

        aliases_set.add(
            self._normalise_name(name)
        )

        if aliases:
            for alias in aliases:
                normalised = self._normalise_name(
                    alias
                )

                if normalised:
                    aliases_set.add(
                        normalised
                    )

        application["aliases"] = sorted(
            aliases_set
        )

        data[
            "applications"
        ][canonical] = application

        self._save(data)

    def register_windows_app(
        self,
        name: str,
        app_id: str,
        aliases: list[str] | None = None,
    ) -> None:
        data = self._load()

        canonical = self._normalise_name(
            name
        )

        application = data[
            "applications"
        ].get(
            canonical,
            {
                "type": "windows_app",
                "app_id": app_id,
                "aliases": [],
            },
        )

        application["type"] = "windows_app"
        application["app_id"] = app_id

        aliases_set = set(
            application.get(
                "aliases",
                [],
            )
        )

        aliases_set.add(
            canonical
        )

        aliases_set.add(
            self._normalise_name(name)
        )

        if aliases:
            for alias in aliases:
                normalised = self._normalise_name(
                    alias
                )

                if normalised:
                    aliases_set.add(
                        normalised
                    )

        application["aliases"] = sorted(
            aliases_set
        )

        data[
            "applications"
        ][canonical] = application

        self._save(data)

    def add_alias(
        self,
        application_name: str,
        alias: str,
    ) -> bool:
        data = self._load()

        canonical = self._find_canonical(
            application_name,
            data,
        )

        if not canonical:
            return False

        normalised = self._normalise_name(
            alias
        )

        if not normalised:
            return False

        aliases = set(
            data[
                "applications"
            ][canonical].get(
                "aliases",
                [],
            )
        )

        aliases.add(
            normalised
        )

        data[
            "applications"
        ][canonical][
            "aliases"
        ] = sorted(
            aliases
        )

        self._save(data)

        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def _find_canonical(
        self,
        name: str,
        data: dict | None = None,
    ) -> str | None:
        if data is None:
            data = self._load()

        requested = self._comparison_name(
            name
        )

        for canonical, details in data.get(
            "applications",
            {},
        ).items():

            if (
                self._comparison_name(
                    canonical
                )
                == requested
            ):
                return canonical

            for alias in details.get(
                "aliases",
                [],
            ):
                if (
                    self._comparison_name(
                        alias
                    )
                    == requested
                ):
                    return canonical

        return None

    def get(
        self,
        name: str,
    ) -> str | None:
        application = self.get_application(
            name
        )

        if not application:
            return None

        if application.get(
            "type"
        ) == "windows_app":
            return application.get(
                "app_id"
            )

        return application.get(
            "executable"
        )

    def get_application(
        self,
        name: str,
    ) -> dict | None:
        data = self._load()

        canonical = self._find_canonical(
            name,
            data,
        )

        if not canonical:
            return None

        application = dict(
            data[
                "applications"
            ][canonical]
        )

        application["name"] = canonical

        return application

    def remove(
        self,
        name: str,
    ) -> bool:
        data = self._load()

        canonical = self._find_canonical(
            name,
            data,
        )

        if not canonical:
            return False

        del data[
            "applications"
        ][canonical]

        self._save(data)

        return True

    def all_apps(self) -> dict:
        return self._load().get(
            "applications",
            {},
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
        name: str,
    ) -> str | None:
        """
        Search Windows broadly.

        Priority:
            1. Windows Start Apps / AppX
            2. PATH
            3. App Paths registry
            4. Start Menu shortcuts
            5. Installed programs
            6. Common executable folders
        """

        requested = self._comparison_name(
            name
        )

        executable_names = (
            self._get_executable_hints(
                name
            )
        )

        # --------------------------------------------------------------
        # 1. Windows Start Apps / AppX
        #
        # This is the important path for things such as:
        #   Snipping Tool
        #   Calculator
        #   Photos
        #   Settings
        # --------------------------------------------------------------

        windows_app = (
            self._discover_windows_start_app(
                requested
            )
        )

        if windows_app:
            return windows_app

        # --------------------------------------------------------------
        # 2. PATH
        # --------------------------------------------------------------

        result = self._discover_from_path(
            executable_names
        )

        if result:
            return result

        # --------------------------------------------------------------
        # 3. App Paths
        # --------------------------------------------------------------

        result = self._discover_from_app_paths(
            executable_names
        )

        if result:
            return result

        # --------------------------------------------------------------
        # 4. Start Menu shortcuts
        # --------------------------------------------------------------

        result = self._discover_from_start_menu(
            requested,
            executable_names,
        )

        if result:
            return result

        # --------------------------------------------------------------
        # 5. Installed desktop programs
        # --------------------------------------------------------------

        result = self._discover_from_installed_apps(
            requested,
            executable_names,
        )

        if result:
            return result

        # --------------------------------------------------------------
        # 6. Common executable locations
        # --------------------------------------------------------------

        result = self._discover_from_common_folders(
            requested,
            executable_names,
        )

        if result:
            return result

        return None

    def discover_and_register(
        self,
        name: str,
    ) -> str | None:
        existing = self.get_application(
            name
        )

        if existing:
            if self._application_is_valid(
                existing
            ):
                return self.get(
                    name
                )

        discovered = (
            self._discover_windows_start_app(
                self._comparison_name(
                    name
                )
            )
        )

        if discovered:
            app_name, app_id = discovered

            self.register_windows_app(
                app_name,
                app_id,
                aliases=[
                    name,
                ],
            )

            return app_id

        executable = self._discover_executable(
            name
        )

        if not executable:
            return None

        executable_path = Path(
            executable
        )

        canonical = self._normalise_name(
            executable_path.stem
        )

        self.register_exe(
            canonical,
            str(executable_path),
            aliases=[
                name,
                canonical,
            ],
        )

        return str(
            executable_path
        )

    # ------------------------------------------------------------------
    # Windows Start Apps
    # ------------------------------------------------------------------

    def _discover_windows_start_app(
        self,
        requested_name: str,
    ) -> tuple[str, str] | None:
        """
        Ask Windows for its own Start Apps catalogue.

        Returns:
            (display_name, app_id)
        """

        script = """
$ErrorActionPreference = 'SilentlyContinue'
Get-StartApps |
    Select-Object Name, AppID |
    ConvertTo-Json -Compress
"""

        result = self._run_hidden(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            timeout=15,
        )

        if result.returncode != 0:
            return None

        raw = result.stdout.strip()

        if not raw:
            return None

        try:
            entries = json.loads(
                raw
            )
        except json.JSONDecodeError:
            return None

        if isinstance(
            entries,
            dict,
        ):
            entries = [
                entries
            ]

        requested_words = set(
            self._comparison_name(
                requested_name
            ).split()
        )

        exact = []
        partial = []

        for entry in entries:
            display_name = str(
                entry.get(
                    "Name",
                    "",
                )
            ).strip()

            app_id = str(
                entry.get(
                    "AppID",
                    "",
                )
            ).strip()

            if not display_name or not app_id:
                continue

            comparison = self._comparison_name(
                display_name
            )

            comparison_words = set(
                comparison.split()
            )

            if comparison == requested_name:
                exact.append(
                    (
                        display_name,
                        app_id,
                    )
                )
                continue

            if requested_words and (
                requested_words
                <= comparison_words
                or comparison_words
                <= requested_words
            ):
                partial.append(
                    (
                        display_name,
                        app_id,
                    )
                )
                continue

            if (
                requested_name
                in comparison
                or comparison
                in requested_name
            ):
                partial.append(
                    (
                        display_name,
                        app_id,
                    )
                )

        if exact:
            return exact[0]

        if partial:
            # Prefer the shortest sensible match.
            partial.sort(
                key=lambda item: len(
                    self._comparison_name(
                        item[0]
                    )
                )
            )

            return partial[0]

        return None

    # ------------------------------------------------------------------
    # Executable discovery
    # ------------------------------------------------------------------

    def _discover_executable(
        self,
        name: str,
    ) -> str | None:
        requested = self._comparison_name(
            name
        )

        executable_names = (
            self._get_executable_hints(
                name
            )
        )

        result = self._discover_from_path(
            executable_names
        )

        if result:
            return result

        result = self._discover_from_app_paths(
            executable_names
        )

        if result:
            return result

        result = self._discover_from_start_menu(
            requested,
            executable_names,
        )

        if result:
            return result

        result = self._discover_from_installed_apps(
            requested,
            executable_names,
        )

        if result:
            return result

        result = self._discover_from_common_folders(
            requested,
            executable_names,
        )

        return result

    # ------------------------------------------------------------------
    # Executable hints
    # ------------------------------------------------------------------

    def _get_executable_hints(
        self,
        name: str,
    ) -> list[str]:
        normalised = self._normalise_name(
            name
        )

        if normalised in self.EXECUTABLE_HINTS:
            return list(
                self.EXECUTABLE_HINTS[
                    normalised
                ]
            )

        comparison = self._comparison_name(
            name
        )

        if comparison == "obs":
            return [
                "obs64.exe",
                "obs.exe",
            ]

        if comparison:
            return [
                f"{comparison}.exe"
            ]

        return []

    # ------------------------------------------------------------------
    # PATH
    # ------------------------------------------------------------------

    def _discover_from_path(
        self,
        executable_names: list[str],
    ) -> str | None:
        for executable_name in executable_names:
            result = self._run_hidden(
                [
                    "where.exe",
                    executable_name,
                ],
                timeout=5,
            )

            if result.returncode != 0:
                continue

            for line in result.stdout.splitlines():
                candidate = Path(
                    line.strip()
                )

                if candidate.is_file():
                    return str(
                        candidate
                    )

        return None

    # ------------------------------------------------------------------
    # App Paths registry
    # ------------------------------------------------------------------

    def _discover_from_app_paths(
        self,
        executable_names: list[str],
    ) -> str | None:
        roots = [
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths",
            r"HKLM\Software\Microsoft\Windows\CurrentVersion\App Paths",
            r"HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ]

        for root in roots:
            for executable_name in executable_names:
                result = self._run_hidden(
                    [
                        "reg.exe",
                        "query",
                        rf"{root}\{executable_name}",
                        "/ve",
                    ]
                )

                if result.returncode != 0:
                    continue

                for line in result.stdout.splitlines():
                    if "REG_SZ" not in line:
                        continue

                    _, value = line.split(
                        "REG_SZ",
                        1,
                    )

                    candidate = Path(
                        value.strip().strip('"')
                    )

                    if candidate.is_file():
                        return str(
                            candidate
                        )

        return None

    # ------------------------------------------------------------------
    # Start Menu shortcuts
    # ------------------------------------------------------------------

    def _discover_from_start_menu(
        self,
        requested_name: str,
        executable_names: list[str],
    ) -> str | None:
        roots = [
            Path(
                os.environ.get(
                    "APPDATA",
                    "",
                )
            )
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs",
            Path(
                os.environ.get(
                    "PROGRAMDATA",
                    r"C:\ProgramData",
                )
            )
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs",
        ]

        requested_words = set(
            requested_name.split()
        )

        for root in roots:
            if not root.exists():
                continue

            try:
                for shortcut in root.rglob(
                    "*.lnk"
                ):
                    shortcut_name = (
                        self._comparison_name(
                            shortcut.stem
                        )
                    )

                    shortcut_words = set(
                        shortcut_name.split()
                    )

                    if not (
                        requested_words
                        <= shortcut_words
                        or shortcut_words
                        <= requested_words
                        or requested_name
                        in shortcut_name
                        or shortcut_name
                        in requested_name
                    ):
                        continue

                    target = (
                        self._resolve_shortcut(
                            shortcut
                        )
                    )

                    if not target:
                        continue

                    target_path = Path(
                        target
                    )

                    if not target_path.is_file():
                        continue

                    if self._executable_matches(
                        target_path,
                        requested_name,
                        executable_names,
                    ):
                        return str(
                            target_path
                        )

            except (
                PermissionError,
                OSError,
            ):
                continue

        return None

    # ------------------------------------------------------------------
    # Installed desktop applications
    # ------------------------------------------------------------------

    def _discover_from_installed_apps(
        self,
        requested_name: str,
        executable_names: list[str],
    ) -> str | None:
        roots = [
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]

        requested_words = set(
            requested_name.split()
        )

        for root in roots:
            result = self._run_hidden(
                [
                    "reg.exe",
                    "query",
                    root,
                    "/s",
                ],
                timeout=20,
            )

            if result.returncode != 0:
                continue

            current_display_name = ""
            current_install_location = ""

            for raw_line in result.stdout.splitlines():
                line = raw_line.strip()

                if line.startswith(
                    "DisplayName"
                ):
                    parts = line.split(
                        "REG_SZ",
                        1,
                    )

                    if len(parts) == 2:
                        current_display_name = (
                            parts[1].strip()
                        )

                elif line.startswith(
                    "InstallLocation"
                ):
                    parts = line.split(
                        "REG_SZ",
                        1,
                    )

                    if len(parts) == 2:
                        current_install_location = (
                            parts[1].strip()
                        )

                    if (
                        current_display_name
                        and current_install_location
                    ):
                        display_name = (
                            self._comparison_name(
                                current_display_name
                            )
                        )

                        display_words = set(
                            display_name.split()
                        )

                        if (
                            requested_words
                            <= display_words
                            or display_words
                            <= requested_words
                            or requested_name
                            in display_name
                            or display_name
                            in requested_name
                        ):
                            candidate = (
                                self._find_matching_executable(
                                    Path(
                                        current_install_location
                                    ),
                                    requested_name,
                                    executable_names,
                                )
                            )

                            if candidate:
                                return candidate

                    current_display_name = ""
                    current_install_location = ""

        return None

    # ------------------------------------------------------------------
    # Common folders
    # ------------------------------------------------------------------

    def _discover_from_common_folders(
        self,
        requested_name: str,
        executable_names: list[str],
    ) -> str | None:
        for root in self.DISCOVERY_ROOTS:
            if not root.exists():
                continue

            try:
                for executable in root.rglob(
                    "*.exe"
                ):
                    if self._executable_matches(
                        executable,
                        requested_name,
                        executable_names,
                    ):
                        return str(
                            executable
                        )

            except (
                PermissionError,
                OSError,
            ):
                continue

        return None

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    @classmethod
    def _executable_matches(
        cls,
        executable: Path,
        requested_name: str,
        executable_names: list[str],
    ) -> bool:
        filename = cls._normalise_name(
            executable.stem
        )

        known = {
            cls._normalise_name(
                Path(name).stem
            )
            for name in executable_names
        }

        if filename in known:
            return True

        requested = cls._comparison_name(
            requested_name
        )

        comparison = cls._comparison_name(
            executable.stem
        )

        comparison_without_digits = re.sub(
            r"\d+$",
            "",
            comparison,
        )

        if (
            comparison_without_digits
            and comparison_without_digits
            == requested
        ):
            return True

        requested_words = set(
            requested.split()
        )

        filename_words = set(
            comparison.split()
        )

        return bool(
            requested_words
            and requested_words
            <= filename_words
        )

    def _find_matching_executable(
        self,
        folder: Path,
        requested_name: str,
        executable_names: list[str],
    ) -> str | None:
        if not folder.exists():
            return None

        try:
            # Exact executable hints first.
            exact_names = {
                name.lower()
                for name in executable_names
            }

            for executable in folder.rglob(
                "*.exe"
            ):
                if (
                    executable.name.lower()
                    in exact_names
                ):
                    return str(
                        executable
                    )

            # Then intelligent matching.
            for executable in folder.rglob(
                "*.exe"
            ):
                if self._executable_matches(
                    executable,
                    requested_name,
                    executable_names,
                ):
                    return str(
                        executable
                    )

        except (
            PermissionError,
            OSError,
        ):
            return None

        return None

    # ------------------------------------------------------------------
    # Shortcut helper
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_shortcut(
        shortcut: Path,
    ) -> str | None:
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "$shell = New-Object "
                "-ComObject WScript.Shell; "
                f"$shortcut = "
                f"$shell.CreateShortcut("
                f"'{shortcut}'); "
                "Write-Output "
                "$shortcut.TargetPath"
            ),
        ]

        result = AppRegistry._run_hidden(
            command,
            timeout=5,
        )

        target = result.stdout.strip()

        return target or None

    # ------------------------------------------------------------------
    # Registry validation
    # ------------------------------------------------------------------

    def _application_is_valid(
        self,
        application: dict,
    ) -> bool:
        application_type = application.get(
            "type",
            "exe",
        )

        if application_type == "windows_app":
            return bool(
                application.get(
                    "app_id"
                )
            )

        executable = application.get(
            "executable"
        )

        if not executable:
            return False

        return Path(
            os.path.expandvars(
                os.path.expanduser(
                    executable
                )
            )
        ).is_file()

    # ------------------------------------------------------------------
    # Hidden subprocess
    # ------------------------------------------------------------------

    @staticmethod
    def _run_hidden(
        command: list[str],
        timeout: int = 5,
    ):
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=timeout,
            )

        except Exception:

            class FailedResult:
                returncode = 1
                stdout = ""
                stderr = ""

            return FailedResult()