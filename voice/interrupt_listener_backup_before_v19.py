from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import pyaudio
from vosk import KaldiRecognizer, Model

from .microphone_manager import MicrophoneDevice, MicrophoneManager
from .speaker import VoiceSpeaker


class InterruptListener:
    """
    Barge-in detector used only while ARIA is speaking.

    Uses the same PyAudio backend and locked microphone as the main
    speech listener. The Vosk model is loaded once and reused.
    """

    MINIMUM_CONFIDENCE = 0.55

    INTERRUPTION_PHRASES = {
        "stop",
        "stop talking",
        "stop speaking",
        "be quiet",
        "quiet",
        "shut up",
    }

    STARTUP_GRACE_SECONDS = 0.20

    def __init__(
        self,
        microphone_manager: MicrophoneManager | None = None,
        model_path: Path | None = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        minimum_confidence: float = MINIMUM_CONFIDENCE,
        on_interrupt: Optional[Callable[[], None]] = None,
        shared_audio=None,
        shared_device: MicrophoneDevice | None = None,
    ) -> None:
        self.microphone_manager = (
            microphone_manager or MicrophoneManager()
        )

        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.minimum_confidence = minimum_confidence
        self.on_interrupt = on_interrupt

        if model_path is None:
            model_path = (
                Path(__file__).resolve().parent
                / "model"
                / "vosk-model-small-en-us-0.15"
            )

        self.model_path = Path(model_path)

        if not self.model_path.exists():
            raise FileNotFoundError(
                "Vosk model not found: "
                f"{self.model_path}"
            )

        print("[BARGE] Loading interruption model...", flush=True)
        self.model = Model(str(self.model_path))

        self._owns_audio = shared_audio is None
        self.audio = shared_audio

        if self.audio is None:
            self.audio = pyaudio.PyAudio()

        self.device: Optional[MicrophoneDevice] = (
            shared_device
            if shared_device is not None
            else self.microphone_manager.get_locked_device()
        )

        if self.device is None:
            raise RuntimeError(
                "ARIA could not find a microphone for interruption detection."
            )

        self.stream = None
        self.recognizer: Optional[KaldiRecognizer] = None

        self.running = False
        self.closed = False
        self.thread: Optional[threading.Thread] = None
        self.started_at = 0.0

    # ================================================================
    # RECOGNIZER
    # ================================================================

    def _create_recognizer(self) -> KaldiRecognizer:
        recognizer = KaldiRecognizer(
            self.model,
            self.sample_rate,
        )

        try:
            recognizer.SetGrammar(
                json.dumps(
                    [
                        "stop",
                        "stop talking",
                        "stop speaking",
                        "be quiet",
                        "quiet",
                        "shut up",
                    ]
                )
            )
        except Exception:
            pass

        try:
            recognizer.SetWords(True)
        except Exception:
            pass

        return recognizer

    # ================================================================
    # MICROPHONE
    # ================================================================

    def _open_stream(self) -> None:
        if self.device is None:
            raise RuntimeError(
                "ARIA has no locked microphone."
            )

        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            input_device_index=self.device.index,
            frames_per_buffer=self.chunk_size,
        )

        print(
            f"[BARGE] Listening on {self.device.name}",
            flush=True,
        )

    # ================================================================
    # TEXT
    # ================================================================

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = (
            text.lower()
            .replace(".", " ")
            .replace(",", " ")
            .replace("!", " ")
            .replace("?", " ")
            .replace("'", " ")
        )

        return " ".join(normalized.split())

    @classmethod
    def _find_phrase(
        cls,
        text: str,
    ) -> Optional[str]:
        normalized = cls._normalize(text)

        if not normalized:
            return None

        words = normalized.split()

        phrases = sorted(
            cls.INTERRUPTION_PHRASES,
            key=lambda phrase: len(phrase.split()),
            reverse=True,
        )

        for phrase in phrases:
            phrase_words = phrase.split()
            length = len(phrase_words)

            for index in range(
                len(words) - length + 1
            ):
                if (
                    words[index:index + length]
                    == phrase_words
                ):
                    return phrase

        return None

    @staticmethod
    def _confidence_for_phrase(
        result: dict,
        phrase: str,
    ) -> float:
        entries = result.get("result", [])

        if not entries:
            return 0.0

        phrase_words = phrase.split()

        recognized = []

        for entry in entries:
            word = str(
                entry.get("word", "")
            ).lower().strip()

            try:
                confidence = float(
                    entry.get("conf", 0.0)
                )
            except (
                TypeError,
                ValueError,
            ):
                confidence = 0.0

            if word:
                recognized.append(
                    (word, confidence)
                )

        if not recognized:
            return 0.0

        for index in range(
            len(recognized) - len(phrase_words) + 1
        ):
            words = [
                word
                for word, _ in recognized[
                    index:index + len(phrase_words)
                ]
            ]

            if words == phrase_words:
                confidences = [
                    confidence
                    for _, confidence in recognized[
                        index:index + len(phrase_words)
                    ]
                ]

                return (
                    min(confidences)
                    if confidences
                    else 0.0
                )

        return 0.0

    # ================================================================
    # LISTEN LOOP
    # ================================================================

    def _listen_loop(self) -> None:
        try:
            self._open_stream()
            self.recognizer = self._create_recognizer()
            self.started_at = time.monotonic()

            while (
                self.running
                and not self.closed
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
                    if not self.running:
                        break
                    continue

                if not self.running:
                    break

                try:
                    accepted = (
                        self.recognizer.AcceptWaveform(
                            data
                        )
                    )

                    if not accepted:
                        continue

                    result = json.loads(
                        self.recognizer.Result()
                    )

                except Exception:
                    continue

                text = (
                    result.get("text", "")
                    .strip()
                    .lower()
                )

                if not text:
                    continue

                if (
                    time.monotonic()
                    - self.started_at
                    < self.STARTUP_GRACE_SECONDS
                ):
                    continue

                phrase = self._find_phrase(text)

                if phrase is None:
                    continue

                confidence = self._confidence_for_phrase(
                    result,
                    phrase,
                )

                print(
                    f"[BARGE] '{phrase}' "
                    f"confidence={confidence:.2f}",
                    flush=True,
                )

                if confidence < self.minimum_confidence:
                    continue

                print(
                    "[BARGE] Interruption confirmed.",
                    flush=True,
                )

                VoiceSpeaker.stop_active()

                if callable(self.on_interrupt):
                    try:
                        self.on_interrupt()
                    except Exception:
                        pass

                self.running = False
                break

        except Exception as exc:
            if self.running:
                print(
                    f"[BARGE] Listener error: {exc}",
                    flush=True,
                )

        finally:
            self._close_stream()

    # ================================================================
    # LIFECYCLE
    # ================================================================

    def start(self) -> None:
        if self.closed or self.running:
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._listen_loop,
            name="ARIA-BargeListener",
            daemon=True,
        )

        self.thread.start()

    def _close_stream(self) -> None:
        stream = self.stream
        self.stream = None

        if stream is None:
            return

        try:
            if stream.is_active():
                stream.stop_stream()
        except Exception:
            pass

        try:
            stream.close()
        except Exception:
            pass

    def stop(self) -> None:
        self.running = False
        self._close_stream()

        if (
            self.thread is not None
            and self.thread.is_alive()
            and self.thread is not threading.current_thread()
        ):
            self.thread.join(timeout=1.0)

        self.thread = None
        self.recognizer = None

    def close(self) -> None:
        if self.closed:
            return

        self.closed = True
        self.stop()

        if self._owns_audio:
            try:
                self.audio.terminate()
            except Exception:
                pass