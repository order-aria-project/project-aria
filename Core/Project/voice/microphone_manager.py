from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import speech_recognition as sr


@dataclass
class MicrophoneDevice:
    index: int
    name: str


class MicrophoneManager:
    """
    Selects and locks ARIA's preferred microphone.

    ARIA prefers the Razer BlackShark microphone. The laptop
    microphone is only used as a fallback when the BlackShark
    cannot actually be opened.

    Once a device has been selected, get_locked_device() keeps
    returning that same device until release_lock() is called.
    This prevents ARIA from silently changing microphones in the
    middle of a conversation.
    """

    PREFERRED_KEYWORDS = (
        "blackshark v3 x",
        "blackshark",
        "razer blackshark",
    )

    LAPTOP_KEYWORDS = (
        "microphone array",
        "intel smart sound",
        "digital microphones",
        "realtek hd audio mic input",
        "realtek hd audio microphone",
    )

    def __init__(
        self,
        preferred_keywords: tuple[str, ...] | None = None,
        fallback_keywords: tuple[str, ...] | None = None,
    ) -> None:
        self.preferred_keywords = (
            preferred_keywords
            or self.PREFERRED_KEYWORDS
        )

        self.fallback_keywords = (
            fallback_keywords
            or self.LAPTOP_KEYWORDS
        )

        self._locked_device: Optional[MicrophoneDevice] = None

    def list_devices(self) -> list[MicrophoneDevice]:
        devices: list[MicrophoneDevice] = []

        names = sr.Microphone.list_microphone_names()

        for index, name in enumerate(names):
            devices.append(
                MicrophoneDevice(
                    index=index,
                    name=name,
                )
            )

        return devices

    def find_preferred_device(
        self,
    ) -> Optional[MicrophoneDevice]:
        devices = self.list_devices()

        for keyword in self.preferred_keywords:
            keyword = keyword.lower()

            for device in devices:
                if keyword in device.name.lower():
                    return device

        return None

    def find_laptop_device(
        self,
    ) -> Optional[MicrophoneDevice]:
        devices = self.list_devices()

        for keyword in self.fallback_keywords:
            keyword = keyword.lower()

            for device in devices:
                if keyword in device.name.lower():
                    return device

        return None

    def select_device(self) -> MicrophoneDevice:
        preferred = self.find_preferred_device()

        if preferred is not None:
            return preferred

        fallback = self.find_laptop_device()

        if fallback is not None:
            return fallback

        raise RuntimeError(
            "ARIA could not find either the "
            "Razer BlackShark microphone or "
            "the laptop microphone."
        )

    def test_device(
        self,
        device: MicrophoneDevice,
    ) -> bool:
        try:
            microphone = sr.Microphone(
                device_index=device.index
            )

            with microphone:
                pass

            return True

        except Exception:
            return False

    def get_working_device(
        self,
    ) -> MicrophoneDevice:
        """
        Prefer BlackShark when it can be opened.

        This performs the fallback decision once. It does not keep
        switching devices during later speech captures.
        """

        preferred = self.find_preferred_device()

        if preferred is not None:
            if self.test_device(preferred):
                return preferred

        fallback = self.find_laptop_device()

        if fallback is not None:
            if self.test_device(fallback):
                return fallback

        raise RuntimeError(
            "ARIA found microphone devices, but "
            "could not open a working microphone."
        )

    def get_locked_device(self) -> MicrophoneDevice:
        """
        Return one stable microphone for the whole ARIA session.
        """

        if self._locked_device is None:
            self._locked_device = (
                self.get_working_device()
            )

        return self._locked_device

    def release_lock(self) -> None:
        self._locked_device = None

    def create_microphone(self) -> sr.Microphone:
        device = self.get_locked_device()

        return sr.Microphone(
            device_index=device.index
        )

    def get_selected_device(
        self,
    ) -> MicrophoneDevice:
        return self.get_locked_device()

    def describe_selected_device(
        self,
    ) -> str:
        device = self.get_locked_device()

        return (
            f"{device.name} "
            f"(device index {device.index})"
        )
