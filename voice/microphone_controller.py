from __future__ import annotations

from typing import Optional

import comtypes
from comtypes import CLSCTX_ALL, POINTER, cast
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume


class MicrophoneController:
    """
    Controls the Windows capture endpoint.

    The controller targets the microphone selected by ARIA's
    MicrophoneManager when possible, while providing a safe fallback
    to the active Windows capture endpoint.
    """

    def __init__(self, preferred_name: str | None = None) -> None:
        self.preferred_name = (
            preferred_name.lower().strip()
            if preferred_name
            else None
        )

    def _get_capture_endpoints(self):
        comtypes.CoInitialize()

        enumerator = (
            AudioUtilities.GetDeviceEnumerator()
        )

        devices = enumerator.EnumAudioEndpoints(
            1,  # eCapture
            1,  # DEVICE_STATE_ACTIVE
        )

        return devices

    def _get_endpoint(self):
        devices = self._get_capture_endpoints()

        preferred = []

        for device in devices:
            try:
                name = device.GetState()

                if name != 1:
                    continue

                friendly_name = ""

                try:
                    friendly_name = str(
                        device.GetFriendlyName()
                    )
                except Exception:
                    pass

                preferred.append(
                    (
                        friendly_name,
                        device,
                    )
                )

            except Exception:
                continue

        # Prefer ARIA's known microphone.
        if self.preferred_name:
            for friendly_name, device in preferred:
                if (
                    self.preferred_name
                    in friendly_name.lower()
                ):
                    return device

        # Otherwise use the first active capture device.
        if preferred:
            return preferred[0][1]

        return None

    def _get_volume(self):
        device = self._get_endpoint()

        if device is None:
            return None

        interface = device.Activate(
            IAudioEndpointVolume._iid_,
            CLSCTX_ALL,
            None,
        )

        return cast(
            interface,
            POINTER(
                IAudioEndpointVolume
            ),
        )

    def mute(self) -> str:
        try:
            endpoint = self._get_volume()

            if endpoint is None:
                return (
                    "STATUS=NOT_FOUND "
                    "No active microphone endpoint was found."
                )

            endpoint.SetMute(
                1,
                None,
            )

            return (
                "STATUS=STARTED "
                "Microphone muted successfully."
            )

        except Exception as exc:
            return (
                "STATUS=FAILED "
                f"Could not mute microphone: {exc}"
            )

        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    def unmute(self) -> str:
        try:
            endpoint = self._get_volume()

            if endpoint is None:
                return (
                    "STATUS=NOT_FOUND "
                    "No active microphone endpoint was found."
                )

            endpoint.SetMute(
                0,
                None,
            )

            return (
                "STATUS=STARTED "
                "Microphone unmuted successfully."
            )

        except Exception as exc:
            return (
                "STATUS=FAILED "
                f"Could not unmute microphone: {exc}"
            )

        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    def is_muted(self) -> Optional[bool]:
        try:
            endpoint = self._get_volume()

            if endpoint is None:
                return None

            return bool(
                endpoint.GetMute()
            )

        except Exception:
            return None

        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass