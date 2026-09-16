from __future__ import annotations

from typing import Optional

import comtypes
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume


class MediaController:
    """
    Controls Windows audio.

    Supports:
    - Global system mute/unmute
    - Per-application mute/unmute
    - Audio-session diagnostics

    Per-application state is saved so ARIA can restore the previous
    mute state rather than blindly forcing every application unmuted.
    """

    APP_ALIASES = {
        "brave": "brave",
        "brave browser": "brave",
        "browser": "brave",
        "chrome": "chrome",
        "google chrome": "chrome",
        "discord": "discord",
        "spotify": "spotify",
        "blender": "blender",
    }

    def __init__(self):
        self._saved_volume: Optional[float] = None
        self._saved_muted: Optional[bool] = None
        self._is_aria_muted = False

        # app key -> {process_id: previous_mute_state}
        self._saved_app_states: dict[str, dict[int, bool]] = {}

    # ---------------------------------------------------------
    # COM helpers
    # ---------------------------------------------------------

    @staticmethod
    def _com_initialize() -> None:
        try:
            comtypes.CoInitialize()
        except Exception:
            pass

    @staticmethod
    def _com_uninitialize() -> None:
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass

    # ---------------------------------------------------------
    # General helpers
    # ---------------------------------------------------------

    @staticmethod
    def _normalise_text(value: object) -> str:
        if value is None:
            return ""

        text = str(value).strip().lower()

        for char in (
            " ",
            "_",
            "-",
            ".",
            "(",
            ")",
            "[",
            "]",
        ):
            text = text.replace(char, "")

        return text

    @classmethod
    def normalise_app_name(cls, name: str) -> str:
        raw = str(name).strip().lower()

        if raw in cls.APP_ALIASES:
            return cls.APP_ALIASES[raw]

        compact = cls._normalise_text(raw)

        for alias, canonical in cls.APP_ALIASES.items():
            if compact == cls._normalise_text(alias):
                return canonical

        return raw

    @staticmethod
    def _safe_process_name(session) -> str:
        try:
            process = session.Process

            if process is None:
                return ""

            try:
                name = process.name()
                if name:
                    return str(name)
            except Exception:
                pass

            try:
                return str(process.name)
            except Exception:
                return ""

        except Exception:
            return ""

    @staticmethod
    def _safe_process_id(session) -> Optional[int]:
        try:
            process = session.Process

            if process is None:
                return None

            try:
                pid = process.pid
                if pid is not None:
                    return int(pid)
            except Exception:
                pass

        except Exception:
            pass

        return None

    @staticmethod
    def _safe_display_name(session) -> str:
        try:
            value = getattr(session, "DisplayName", None)

            if value:
                return str(value)

        except Exception:
            pass

        return ""

    @staticmethod
    def _safe_icon_path(session) -> str:
        try:
            value = getattr(session, "IconPath", None)

            if value:
                return str(value)

        except Exception:
            pass

        return ""

    @classmethod
    def _session_matches_app(cls, session, app_name: str) -> bool:
        target = cls.normalise_app_name(app_name)

        process_name = cls._safe_process_name(session)
        display_name = cls._safe_display_name(session)
        icon_path = cls._safe_icon_path(session)

        process_base = process_name.lower().replace(".exe", "")
        display_lower = display_name.lower()
        icon_lower = icon_path.lower()

        # Direct process match.
        if process_base == target:
            return True

        # Loose process matching.
        if target in process_base:
            return True

        # Display-name matching.
        if target in display_lower:
            return True

        # Icon path often contains the executable path.
        if target in icon_lower:
            return True

        # Browser-specific fallback.
        if target == "brave":
            brave_tokens = (
                "brave",
                "brave browser",
            )

            if any(token in process_base for token in brave_tokens):
                return True

            if any(token in display_lower for token in brave_tokens):
                return True

            if any(token in icon_lower for token in brave_tokens):
                return True

        if target == "chrome":
            chrome_tokens = (
                "chrome",
                "google chrome",
            )

            if any(token in process_base for token in chrome_tokens):
                return True

            if any(token in display_lower for token in chrome_tokens):
                return True

            if any(token in icon_lower for token in chrome_tokens):
                return True

        return False

    @classmethod
    def _get_all_sessions(cls):
        return AudioUtilities.GetAllSessions()

    @classmethod
    def _find_app_sessions(cls, app_name: str):
        sessions = []

        for session in cls._get_all_sessions():
            try:
                if session is None:
                    continue

                if cls._session_matches_app(session, app_name):
                    sessions.append(session)

            except Exception:
                continue

        return sessions

    # ---------------------------------------------------------
    # Global system audio
    # ---------------------------------------------------------

    @staticmethod
    def _get_volume_interface():
        device = AudioUtilities.GetSpeakers()

        if hasattr(device, "EndpointVolume"):
            return device.EndpointVolume

        if hasattr(device, "Activate"):
            interface = device.Activate(
                IAudioEndpointVolume._iid_,
                comtypes.CLSCTX_ALL,
                None,
            )
            return interface.QueryInterface(IAudioEndpointVolume)

        raise RuntimeError(
            "Windows speaker endpoint does not expose IAudioEndpointVolume."
        )

    def mute(self) -> bool:
        self._com_initialize()

        try:
            volume = self._get_volume_interface()

            if not self._is_aria_muted:
                try:
                    self._saved_volume = float(volume.GetMasterVolumeLevelScalar())
                except Exception:
                    self._saved_volume = None

                try:
                    self._saved_muted = bool(volume.GetMute())
                except Exception:
                    self._saved_muted = False

            volume.SetMute(1, None)
            self._is_aria_muted = True

            print("[MEDIA] Windows audio muted by ARIA.")
            return True

        except Exception as exc:
            print(f"[MEDIA] Global mute failed: {exc}")
            return False

        finally:
            self._com_uninitialize()

    def unmute(self) -> bool:
        self._com_initialize()

        try:
            volume = self._get_volume_interface()

            if self._is_aria_muted:
                if self._saved_volume is not None:
                    try:
                        volume.SetMasterVolumeLevelScalar(
                            self._saved_volume,
                            None,
                        )
                    except Exception:
                        pass

                if self._saved_muted is not None:
                    try:
                        volume.SetMute(
                            1 if self._saved_muted else 0,
                            None,
                        )
                    except Exception:
                        pass
                else:
                    volume.SetMute(0, None)

            else:
                volume.SetMute(0, None)

            self._is_aria_muted = False

            print("[MEDIA] Previous Windows audio state restored.")
            return True

        except Exception as exc:
            print(f"[MEDIA] Global unmute failed: {exc}")
            return False

        finally:
            self._com_uninitialize()

    # ---------------------------------------------------------
    # Application audio
    # ---------------------------------------------------------

    def mute_application(self, app_name: str) -> bool:
        self._com_initialize()

        try:
            canonical = self.normalise_app_name(app_name)

            sessions = self._find_app_sessions(canonical)

            if not sessions:
                print(
                    f"[MEDIA] No active audio session found for "
                    f"{app_name}."
                )
                print("[MEDIA] Current Windows audio sessions:")

                self._print_session_diagnostics()

                return False

            saved_states = self._saved_app_states.setdefault(
                canonical,
                {},
            )

            muted_count = 0

            for session in sessions:
                try:
                    pid = self._safe_process_id(session)

                    volume = getattr(session, "SimpleAudioVolume", None)

                    if volume is None:
                        continue

                    if pid is not None and pid not in saved_states:
                        try:
                            saved_states[pid] = bool(volume.GetMute())
                        except Exception:
                            saved_states[pid] = False

                    volume.SetMute(1, None)

                    muted_count += 1

                    process_name = self._safe_process_name(session)
                    display_name = self._safe_display_name(session)

                    print(
                        "[MEDIA] Muted session: "
                        f"process={process_name or 'unknown'} "
                        f"display={display_name or 'unknown'} "
                        f"pid={pid if pid is not None else 'unknown'}"
                    )

                except Exception as exc:
                    print(
                        f"[MEDIA] Failed to mute one session: {exc}"
                    )

            if muted_count == 0:
                print(
                    f"[MEDIA] Found {len(sessions)} matching session(s), "
                    f"but none could be muted."
                )
                return False

            print(
                f"[MEDIA] {canonical.title()} muted "
                f"({muted_count} audio session(s))."
            )

            return True

        except Exception as exc:
            print(
                f"[MEDIA] Application mute failed: {exc}"
            )
            return False

        finally:
            self._com_uninitialize()

    def unmute_application(self, app_name: str) -> bool:
        self._com_initialize()

        try:
            canonical = self.normalise_app_name(app_name)

            sessions = self._find_app_sessions(canonical)

            if not sessions:
                print(
                    f"[MEDIA] No active audio session found for "
                    f"{app_name}."
                )
                return False

            saved_states = self._saved_app_states.get(canonical, {})

            changed_count = 0

            for session in sessions:
                try:
                    pid = self._safe_process_id(session)

                    volume = getattr(session, "SimpleAudioVolume", None)

                    if volume is None:
                        continue

                    previous_state = False

                    if pid is not None and pid in saved_states:
                        previous_state = saved_states[pid]

                    volume.SetMute(
                        1 if previous_state else 0,
                        None,
                    )

                    changed_count += 1

                    print(
                        "[MEDIA] Restored session: "
                        f"process={self._safe_process_name(session) or 'unknown'} "
                        f"pid={pid if pid is not None else 'unknown'}"
                    )

                except Exception as exc:
                    print(
                        f"[MEDIA] Failed to restore one session: {exc}"
                    )

            if canonical in self._saved_app_states:
                del self._saved_app_states[canonical]

            if changed_count == 0:
                print(
                    f"[MEDIA] No matching audio sessions could be restored "
                    f"for {app_name}."
                )
                return False

            print(
                f"[MEDIA] {canonical.title()} audio restored."
            )

            return True

        except Exception as exc:
            print(
                f"[MEDIA] Application unmute failed: {exc}"
            )
            return False

        finally:
            self._com_uninitialize()

    # ---------------------------------------------------------
    # Diagnostics
    # ---------------------------------------------------------

    def _print_session_diagnostics(self) -> None:
        try:
            sessions = self._get_all_sessions()

            found = 0

            for session in sessions:
                try:
                    if session is None:
                        continue

                    process_name = self._safe_process_name(session)
                    display_name = self._safe_display_name(session)
                    pid = self._safe_process_id(session)

                    # Skip completely empty sessions.
                    if not process_name and not display_name:
                        continue

                    found += 1

                    print(
                        "[MEDIA SESSION] "
                        f"process={process_name or 'unknown'} | "
                        f"display={display_name or 'unknown'} | "
                        f"pid={pid if pid is not None else 'unknown'}"
                    )

                except Exception:
                    continue

            if found == 0:
                print("[MEDIA] No readable audio sessions found.")

        except Exception as exc:
            print(
                f"[MEDIA] Session diagnostics failed: {exc}"
            )

    def list_applications(self):
        self._com_initialize()

        try:
            results = []

            for session in self._get_all_sessions():
                try:
                    if session is None:
                        continue

                    process_name = self._safe_process_name(session)
                    display_name = self._safe_display_name(session)
                    pid = self._safe_process_id(session)

                    if not process_name and not display_name:
                        continue

                    results.append(
                        {
                            "process": process_name,
                            "display": display_name,
                            "pid": pid,
                        }
                    )

                except Exception:
                    continue

            return results

        finally:
            self._com_uninitialize()

    def close(self) -> None:
        self._saved_app_states.clear()
        self._saved_volume = None
        self._saved_muted = None
        self._is_aria_muted = False