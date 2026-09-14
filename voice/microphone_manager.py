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
    Chooses the best available microphone for ARIA.

    Preferred device:
        Razer BlackShark V3 X

    Fallback:
        Laptop internal microphone array

    The manager does not permanently depend on a microphone index.
    It searches by device name each time it needs to choose an input.
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

    def list_devices(self) -> list[MicrophoneDevice]:
        devices: list[
            MicrophoneDevice
        ] = []

        names = (
            sr.Microphone.list_microphone_names()
        )

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

    def select_device(
        self,
    ) -> MicrophoneDevice:
        """
        Select the preferred headset microphone when available.

        Otherwise select the laptop microphone array.

        Raises:
            RuntimeError: when neither microphone can be found.
        """

        preferred = (
            self.find_preferred_device()
        )

        if preferred is not None:
            return preferred

        fallback = (
            self.find_laptop_device()
        )

        if fallback is not None:
            return fallback

        raise RuntimeError(
            "ARIA could not find either the "
            "Razer BlackShark microphone or "
            "the laptop microphone."
        )

    def create_microphone(
        self,
    ) -> sr.Microphone:
        device = self.select_device()

        return sr.Microphone(
            device_index=device.index
        )

    def get_selected_device(
        self,
    ) -> MicrophoneDevice:
        return self.select_device()

    def describe_selected_device(
        self,
    ) -> str:
        device = self.select_device()

        return (
            f"{device.name} "
            f"(device index {device.index})"
        )

    def test_device(
        self,
        device: MicrophoneDevice,
    ) -> bool:
        """
        Open the microphone once to verify that the
        selected Windows audio input is actually usable.

        Returns True when the device can be opened.
        """

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
        Prefer the BlackShark when it can actually be opened.
        Fall back to the laptop microphone if necessary.
        """

        preferred = (
            self.find_preferred_device()
        )

        if preferred is not None:
            if self.test_device(preferred):
                return preferred

        fallback = (
            self.find_laptop_device()
        )

        if fallback is not None:
            if self.test_device(fallback):
                return fallback

        raise RuntimeError(
            "ARIA found microphone devices, but "
            "could not open a working microphone."
        )