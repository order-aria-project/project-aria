from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import pyaudio
from vosk import KaldiRecognizer, Model

from .microphone_manager import (
    MicrophoneDevice,
    MicrophoneManager,
)


class WakeWordListener:
    """
    Lightweight offline wake-word detector.

    One spoken "ARIA" produces one detection.

    The microphone can be paused while Whisper records the
    command and resumed afterward.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        microphone_manager: MicrophoneManager | None = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        rearm_seconds: float = 0.8,
    ) -> None:

        self.microphone_manager = (
            microphone_manager
            or MicrophoneManager()
        )

        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.rearm_seconds = rearm_seconds

        if model_path is None:
            model_path = (
                Path(__file__).resolve().parent
                / "model"
                / "vosk-model-small-en-us-0.15"
            )

        self.model_path = Path(model_path)

        if not self.model_path.exists():
            raise FileNotFoundError(
                "Wake-word model not found: "
                f"{self.model_path}"
            )

        print(
            f"Loading wake-word model:\n"
            f"{self.model_path}",
            flush=True,
        )

        self.model = Model(
            str(self.model_path)
        )

        self.audio = pyaudio.PyAudio()

        self.device: Optional[
            MicrophoneDevice
        ] = None

        self.stream = None
        self.recognizer: Optional[
            KaldiRecognizer
        ] = None

        self.armed = True
        self.non_wake_since: Optional[
            float
        ] = None

        self.closed = False
        self.paused = False

    def _get_microphone(
        self,
    ) -> Optional[MicrophoneDevice]:

        preferred = (
            self.microphone_manager
            .find_preferred_device()
        )

        if preferred is not None:
            return preferred

        return (
            self.microphone_manager
            .find_laptop_device()
        )

    def _create_recognizer(
        self,
    ) -> KaldiRecognizer:

        recognizer = KaldiRecognizer(
            self.model,
            self.sample_rate,
        )

        try:
            recognizer.SetGrammar(
                '["aria", "[unk]"]'
            )
        except Exception:
            pass

        return recognizer

    def start(self) -> None:

        if self.closed:
            return

        if self.stream is not None:
            return

        if self.device is None:
            self.device = self._get_microphone()

        if self.device is None:
            raise RuntimeError(
                "ARIA could not find a microphone "
                "for wake-word detection."
            )

        if self.recognizer is None:
            self.recognizer = (
                self._create_recognizer()
            )

        try:

            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.device.index,
                frames_per_buffer=self.chunk_size,
            )

        except Exception as exc:

            self.stream = None

            raise RuntimeError(
                "ARIA could not open the "
                f"wake-word microphone: {exc}"
            ) from exc

        self.paused = False

        print(
            f"[WAKE] Listening through: "
            f"{self.device.name}",
            flush=True,
        )

        print(
            "[WAKE] Waiting for 'ARIA'...",
            flush=True,
        )

    def pause(self) -> None:
        """
        Temporarily release the microphone.
        """

        if self.stream is None:
            self.paused = True
            return

        stream = self.stream
        self.stream = None
        self.paused = True

        try:
            if stream.is_active():
                stream.stop_stream()
        except (
            Exception,
            KeyboardInterrupt,
        ):
            pass

        try:
            stream.close()
        except (
            Exception,
            KeyboardInterrupt,
        ):
            pass

    def resume(self) -> None:
        """
        Resume wake-word detection.
        """

        if self.closed:
            return

        if not self.paused and self.stream is not None:
            return

        self.start()

    def listen_once(self) -> bool:

        if self.closed:
            return False

        self.start()

        while (
            not self.closed
            and self.stream is not None
            and self.recognizer is not None
        ):

            try:

                data = self.stream.read(
                    self.chunk_size,
                    exception_on_overflow=False,
                )

            except (
                OSError,
                IOError,
            ):

                if self.closed:
                    return False

                continue

            if self.closed:
                return False

            text = ""

            try:

                if self.recognizer.AcceptWaveform(
                    data
                ):

                    result = json.loads(
                        self.recognizer.Result()
                    )

                    text = (
                        result
                        .get("text", "")
                        .strip()
                        .lower()
                    )

                else:

                    result = json.loads(
                        self.recognizer.PartialResult()
                    )

                    text = (
                        result
                        .get("partial", "")
                        .strip()
                        .lower()
                    )

            except Exception:

                if self.closed:
                    return False

                continue

            detected = (
                self._contains_wake_word(text)
            )

            now = time.monotonic()

            if self.armed:

                if detected:

                    self.armed = False
                    self.non_wake_since = None

                    print(
                        "[WAKE] ARIA detected.",
                        flush=True,
                    )

                    return True

                continue

            if detected:

                self.non_wake_since = None
                continue

            if self.non_wake_since is None:

                self.non_wake_since = now

                continue

            if (
                now - self.non_wake_since
                >= self.rearm_seconds
            ):

                self.armed = True
                self.non_wake_since = None

                print(
                    "[WAKE] Detector re-armed.",
                    flush=True,
                )

        return False

    @staticmethod
    def _contains_wake_word(
        text: str,
    ) -> bool:

        if not text:
            return False

        normalized = (
            text.lower()
            .replace(".", " ")
            .replace(",", " ")
            .replace("!", " ")
            .replace("?", " ")
            .strip()
        )

        return "aria" in normalized.split()

    def close(self) -> None:
        """
        Safely release all wake-word resources.

        Shutdown must never turn into another traceback.
        """

        if self.closed:
            return

        self.closed = True
        self.paused = True

        stream = self.stream
        self.stream = None

        if stream is not None:

            try:
                if stream.is_active():
                    stream.stop_stream()
            except (
                Exception,
                KeyboardInterrupt,
            ):
                pass

            try:
                stream.close()
            except (
                Exception,
                KeyboardInterrupt,
            ):
                pass

        try:
            self.audio.terminate()
        except (
            Exception,
            KeyboardInterrupt,
        ):
            pass