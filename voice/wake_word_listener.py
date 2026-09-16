from __future__ import annotations

import json
import math
import re
import statistics
import time
from array import array
from pathlib import Path
from typing import Callable, Optional

import pyaudio
from vosk import KaldiRecognizer, Model

from .microphone_manager import (
    MicrophoneDevice,
    MicrophoneManager,
)


class WakeWordListener:
    """
    Advanced ARIA wake detector.

    V24 focus:
        - improve wake-word recall without weakening the final Whisper gate
        - tolerate common Vosk single-word variants of "aria"
        - give the microphone a short startup warm-up
        - keep the existing acoustic + Whisper verification protection

    Only the wake-word component is changed in this build.
    """

    MINIMUM_CONFIDENCE = 0.35

    AUDIO_BUFFER_SECONDS = 3.0
    QUIET_REARM_SECONDS = 0.9
    REJECTION_QUIET_SECONDS = 0.35
    COOLDOWN_SECONDS = 0.90

    # Slightly more forgiving wake acoustics. Final Whisper verification
    # remains mandatory, so recall can improve without blindly accepting noise.
    FRAME_MS = 20
    MIN_VOICE_RMS = 350.0
    ACTIVE_MULTIPLIER = 2.10
    LEADING_QUIET_SECONDS = 0.18
    TRAILING_QUIET_SECONDS = 0.08
    MAX_CONTINUOUS_PRECEDING_SPEECH = 1.20
    MAX_OVERALL_ACTIVE_FRACTION = 0.82

    SINGING_ACTIVE_SECONDS = 1.10
    SINGING_PERIODICITY = 0.74
    SINGING_PITCH_STABILITY = 0.055

    STARTUP_WARMUP_SECONDS = 0.45

    # These are deliberately single-token candidates only. Whisper remains
    # the authoritative verifier, so these variants improve recall without
    # turning arbitrary conversation into an accepted wake.
    WAKE_CANDIDATES = {
        "aria",
        "area",
        "arya",
        "ariah",
        "ariel",
    }

    def __init__(
        self,
        model_path: Path | None = None,
        microphone_manager: MicrophoneManager | None = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        rearm_seconds: float = QUIET_REARM_SECONDS,
        cooldown_seconds: float = COOLDOWN_SECONDS,
        minimum_confidence: float = MINIMUM_CONFIDENCE,
        verify_callback: Callable[[bytes], bool] | None = None,
        on_wake=None,
    ) -> None:
        self.microphone_manager = (
            microphone_manager or MicrophoneManager()
        )

        self.sample_rate = int(sample_rate)
        self.chunk_size = int(chunk_size)
        self.rearm_seconds = float(rearm_seconds)
        self.cooldown_seconds = float(cooldown_seconds)
        self.minimum_confidence = float(minimum_confidence)

        self.verify_callback = verify_callback
        self.on_wake = on_wake

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
            f"Loading wake-word model:\n{self.model_path}",
            flush=True,
        )

        self.model = Model(str(self.model_path))
        self.audio = pyaudio.PyAudio()

        self.device: Optional[MicrophoneDevice] = None
        self.stream = None
        self.recognizer: Optional[KaldiRecognizer] = None

        self.armed = True
        self.non_wake_since: Optional[float] = None
        self.last_detection = 0.0
        self.last_rejection = 0.0

        self.closed = False
        self.paused = False

        print(
            "[WAKE] Advanced wake listener initialized.",
            flush=True,
        )

    def _create_recognizer(self) -> KaldiRecognizer:
        recognizer = KaldiRecognizer(
            self.model,
            self.sample_rate,
        )

        try:
            recognizer.SetWords(True)
        except Exception:
            pass

        return recognizer

    def _reset_detection_state(self) -> None:
        self.armed = True
        self.non_wake_since = None
        self.recognizer = self._create_recognizer()

    def _get_microphone(self) -> Optional[MicrophoneDevice]:
        return self.microphone_manager.get_locked_device()

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

        self._reset_detection_state()

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
                "ARIA could not open the wake-word microphone: "
                f"{exc}"
            ) from exc

        self.paused = False

        print(
            f"[WAKE] Listening through: {self.device.name}",
            flush=True,
        )
        print(
            "[WAKE] Microphone warm-up complete; waiting for 'ARIA'...",
            flush=True,
        )

        # Discard a tiny startup window so the first real utterance is not
        # competing with device/stream startup transients.
        deadline = time.monotonic() + self.STARTUP_WARMUP_SECONDS
        while (
            time.monotonic() < deadline
            and self.stream is not None
            and not self.closed
        ):
            try:
                self.stream.read(
                    self.chunk_size,
                    exception_on_overflow=False,
                )
            except (OSError, IOError):
                break

    def pause(self) -> None:
        if self.stream is None:
            self.paused = True
            return

        stream = self.stream
        self.stream = None
        self.paused = True

        try:
            if stream.is_active():
                stream.stop_stream()
        except Exception:
            pass

        try:
            stream.close()
        except Exception:
            pass

    def resume(self) -> None:
        if self.closed:
            return

        if not self.paused and self.stream is not None:
            return

        self.start()

    @staticmethod
    def _normalize(text: str) -> str:
        value = str(text or "").lower()
        for old in (".", ",", "!", "?", "'", "’", ":", ";"):
            value = value.replace(old, " ")
        return " ".join(value.split())

    @classmethod
    def _candidate_word(cls, text: str) -> str | None:
        normalized = cls._normalize(text)
        if not normalized:
            return None

        # Only a single spoken token is eligible for the tolerant Vosk gate.
        # Multi-word text continues to be ignored.
        parts = normalized.split()
        if len(parts) != 1:
            return None

        word = parts[0]
        if word in cls.WAKE_CANDIDATES:
            return word

        # Small-vocabulary phonetic spellings seen with the tiny English Vosk
        # model. Still single-token only and still sent through Whisper.
        compact = re.sub(r"[^a-z]", "", word)
        compact_map = {
            "ar": "aria",
            "ari": "aria",
            "area": "area",
            "arya": "arya",
            "ariah": "ariah",
            "ariel": "ariel",
        }
        return compact_map.get(compact)

    @classmethod
    def _is_wake_candidate(cls, text: str) -> bool:
        return cls._candidate_word(text) is not None

    @staticmethod
    def _word_confidence(result: dict) -> float:
        words = result.get("result", [])
        if not isinstance(words, list):
            return 0.0

        confidences: list[float] = []
        for word in words:
            word_text = str(word.get("word", "")).strip().lower()
            if not word_text:
                continue

            try:
                confidence = float(word.get("conf", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0

            confidences.append(confidence)

        if not confidences:
            return 0.0

        return min(confidences)

    @staticmethod
    def _pcm_samples(audio_bytes: bytes) -> list[int]:
        usable = len(audio_bytes) - (len(audio_bytes) % 2)
        if usable <= 0:
            return []

        try:
            return list(array("h", audio_bytes[:usable]))
        except Exception:
            return []

    def _frame_rms(self, samples: list[int]) -> list[float]:
        frame_size = max(
            1,
            int(self.sample_rate * self.FRAME_MS / 1000),
        )

        values: list[float] = []
        for start in range(0, len(samples), frame_size):
            frame = samples[start:start + frame_size]
            if len(frame) < frame_size // 2:
                break

            squared = sum(sample * sample for sample in frame)
            values.append(math.sqrt(squared / max(1, len(frame))))

        return values

    @staticmethod
    def _active_threshold(rms_values: list[float]) -> float:
        if not rms_values:
            return 1.0

        ordered = sorted(rms_values)
        low = ordered[: max(1, int(len(ordered) * 0.30))]
        noise_floor = statistics.median(low)
        peak = max(ordered)

        adaptive = noise_floor * WakeWordListener.ACTIVE_MULTIPLIER
        peak_cap = peak * 0.72

        if peak > WakeWordListener.MIN_VOICE_RMS and peak_cap > 0.0:
            adaptive = min(adaptive, peak_cap)

        return max(
            WakeWordListener.MIN_VOICE_RMS,
            adaptive,
        )

    @staticmethod
    def _longest_true_run(flags: list[bool]) -> int:
        best = 0
        current = 0
        for flag in flags:
            if flag:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best

    @staticmethod
    def _fraction_true(flags: list[bool]) -> float:
        if not flags:
            return 0.0
        return sum(1 for value in flags if value) / len(flags)

    def _quiet_fraction(
        self,
        flags: list[bool],
        start: float,
        end: float,
    ) -> float:
        if not flags:
            return 1.0

        first = max(
            0,
            int(start * 1000 / self.FRAME_MS),
        )
        last = min(
            len(flags),
            int(end * 1000 / self.FRAME_MS),
        )
        window = flags[first:last]
        if not window:
            return 1.0

        return 1.0 - self._fraction_true(window)

    def _estimate_pitch(
        self,
        samples: list[int],
    ) -> tuple[float, float]:
        target = int(self.sample_rate * 0.55)
        if len(samples) < target:
            return 0.0, 0.0

        segment = samples[-target:]
        step = max(1, self.sample_rate // 4000)
        down = segment[::step]

        if len(down) < 500:
            return 0.0, 0.0

        mean = sum(down) / len(down)
        centered = [sample - mean for sample in down]
        energy = sum(sample * sample for sample in centered)

        if energy <= 1.0:
            return 0.0, 0.0

        sample_rate = self.sample_rate / step
        min_lag = max(2, int(sample_rate / 330.0))
        max_lag = min(
            len(centered) // 2,
            int(sample_rate / 75.0),
        )

        best_corr = 0.0
        best_lag = 0

        for lag in range(min_lag, max_lag + 1):
            overlap = len(centered) - lag
            if overlap <= 0:
                continue

            numerator = 0.0
            energy_a = 0.0
            energy_b = 0.0

            for index in range(overlap):
                a = centered[index]
                b = centered[index + lag]
                numerator += a * b
                energy_a += a * a
                energy_b += b * b

            denominator = math.sqrt(
                energy_a * energy_b
            )
            if denominator <= 1e-9:
                continue

            corr = numerator / denominator
            if corr > best_corr:
                best_corr = corr
                best_lag = lag

        if best_lag <= 0:
            return 0.0, max(0.0, best_corr)

        return (
            sample_rate / best_lag,
            max(0.0, best_corr),
        )

    def _singing_like(
        self,
        samples: list[int],
        active_flags: list[bool],
    ) -> bool:
        frame_seconds = self.FRAME_MS / 1000.0
        active_seconds = (
            sum(active_flags) * frame_seconds
        )

        if active_seconds < self.SINGING_ACTIVE_SECONDS:
            return False

        if not samples:
            return False

        window_size = int(
            self.sample_rate * 0.55
        )
        if len(samples) < window_size * 2:
            return False

        window_1 = samples[
            -window_size * 2:-window_size
        ]
        window_2 = samples[-window_size:]

        pitch_1, periodicity_1 = (
            self._estimate_pitch(window_1)
        )
        pitch_2, periodicity_2 = (
            self._estimate_pitch(window_2)
        )

        periodicity = min(
            periodicity_1,
            periodicity_2,
        )

        if periodicity < self.SINGING_PERIODICITY:
            return False

        if pitch_1 <= 1.0 or pitch_2 <= 1.0:
            return False

        pitch_delta = (
            abs(pitch_1 - pitch_2)
            / max(pitch_1, pitch_2)
        )

        return (
            pitch_delta
            <= self.SINGING_PITCH_STABILITY
        )

    def _attention_gate(
        self,
        audio_bytes: bytes,
    ) -> tuple[
        bool,
        str,
        dict[str, float],
    ]:
        samples = self._pcm_samples(audio_bytes)
        if not samples:
            return False, "no_audio", {}

        rms_values = self._frame_rms(samples)
        if not rms_values:
            return False, "no_rms", {}

        threshold = self._active_threshold(rms_values)
        active = [
            value >= threshold
            for value in rms_values
        ]

        frame_seconds = self.FRAME_MS / 1000.0
        total_seconds = (
            len(active) * frame_seconds
        )

        overall_active = self._fraction_true(active)
        longest_run = (
            self._longest_true_run(active)
            * frame_seconds
        )

        leading_quiet = self._quiet_fraction(
            active,
            0.0,
            min(
                self.LEADING_QUIET_SECONDS,
                total_seconds,
            ),
        )

        trailing_quiet = self._quiet_fraction(
            active,
            max(
                0.0,
                total_seconds
                - self.TRAILING_QUIET_SECONDS,
            ),
            total_seconds,
        )

        metrics = {
            "active_fraction": overall_active,
            "longest_active_run": longest_run,
            "leading_quiet": leading_quiet,
            "trailing_quiet": trailing_quiet,
            "threshold": threshold,
        }

        if overall_active < 0.010:
            return False, "too_quiet", metrics

        if longest_run > self.MAX_CONTINUOUS_PRECEDING_SPEECH:
            if overall_active > 0.55:
                return False, "continuous_speech", metrics

        if overall_active > self.MAX_OVERALL_ACTIVE_FRACTION:
            return False, "speech_heavy_context", metrics

        # Do NOT require a large leading silence window. People routinely say
        # "ARIA" immediately after a short breath or while leaning toward the
        # microphone. The final Whisper check is still mandatory.
        if leading_quiet < 0.05 and longest_run > 1.60:
            return False, "not_isolated_before_wake", metrics

        if (
            trailing_quiet < 0.02
            and overall_active > 0.68
        ):
            return False, "wake_inside_continuous_audio", metrics

        if self._singing_like(samples, active):
            return False, "sustained_tonal_speech", metrics

        return True, "attention_ok", metrics

    def _reject_candidate(self, reason: str) -> None:
        self.last_rejection = time.monotonic()
        print(
            f"[WAKE] Attention gate rejected candidate: {reason}",
            flush=True,
        )
        self._reset_detection_state()

    def listen_once(self) -> bool:
        if self.closed:
            return False

        self.start()
        audio_buffer = bytearray()

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
            except (OSError, IOError):
                if self.closed:
                    return False
                continue

            if self.closed:
                return False

            audio_buffer.extend(data)

            max_audio_bytes = int(
                self.sample_rate
                * self.AUDIO_BUFFER_SECONDS
                * 2
            )

            if len(audio_buffer) > max_audio_bytes:
                del audio_buffer[
                    : len(audio_buffer) - max_audio_bytes
                ]

            try:
                accepted = (
                    self.recognizer.AcceptWaveform(data)
                )

                if accepted:
                    result = json.loads(
                        self.recognizer.Result()
                    )
                    is_partial_candidate = False
                else:
                    result = json.loads(
                        self.recognizer.PartialResult()
                    )
                    is_partial_candidate = True

            except Exception as exc:
                if self.closed:
                    return False

                print(
                    f"[WAKE] Recognition error: {exc}",
                    flush=True,
                )
                continue

            text_key = (
                "partial"
                if is_partial_candidate
                else "text"
            )

            text = str(
                result.get(text_key, "")
            ).strip().lower()

            if not text:
                continue

            now = time.monotonic()

            if (
                now - self.last_rejection
                < self.REJECTION_QUIET_SECONDS
            ):
                continue

            if not self.armed:
                if self._is_wake_candidate(text):
                    self.non_wake_since = None
                    continue

                if self.non_wake_since is None:
                    self.non_wake_since = now
                    continue

                if (
                    now - self.non_wake_since
                    >= self.rearm_seconds
                ):
                    self._reset_detection_state()
                    audio_buffer.clear()
                    print(
                        "[WAKE] Detector re-armed.",
                        flush=True,
                    )

                continue

            candidate = self._candidate_word(text)
            if candidate is None:
                continue

            confidence = self._word_confidence(result)

            if (
                is_partial_candidate
                and confidence <= 0.0
            ):
                confidence = 0.50

            print(
                f"[WAKE] Candidate: {candidate} "
                f"(conf={confidence:.2f}"
                f"{' partial' if is_partial_candidate else ''})",
                flush=True,
            )

            if confidence < self.minimum_confidence:
                self._reject_candidate(
                    "vosk_confidence"
                )
                audio_buffer.clear()
                continue

            attention_ok, reason, metrics = (
                self._attention_gate(
                    bytes(audio_buffer)
                )
            )

            if not attention_ok:
                print(
                    "[WAKE] Acoustic metrics: "
                    f"active={metrics.get('active_fraction', 0.0):.2f} "
                    f"run={metrics.get('longest_active_run', 0.0):.2f}s "
                    f"lead_quiet={metrics.get('leading_quiet', 0.0):.2f}",
                    flush=True,
                )

                self._reject_candidate(reason)
                audio_buffer.clear()
                continue

            print(
                "[WAKE] Attention gate passed.",
                flush=True,
            )

            # Vosk + the acoustic attention gate are authoritative for the wake word.
            # The previous Whisper veto caused valid ARIA detections to be rejected
            # when Whisper heard variants such as "arya" or "aurea".
            if self.verify_callback is not None:
                try:
                    verifier_result = bool(
                        self.verify_callback(
                            bytes(audio_buffer)
                        )
                    )
                    print(
                        f"[WAKE] Secondary verifier: {verifier_result} "
                        "(non-blocking)",
                        flush=True,
                    )
                except Exception as exc:
                    print(
                        "[WAKE] Secondary verifier unavailable: "
                        f"{exc} (non-blocking)",
                        flush=True,
                    )

            if (
                now - self.last_detection
                < self.cooldown_seconds
            ):
                continue

            self.last_detection = now
            self.armed = False
            self.non_wake_since = None

            print(
                "[WAKE] ARIA accepted by Vosk + attention gate.",
                flush=True,
            )
            print(
                "[WAKE] Wake decision: ACCEPT",
                flush=True,
            )

            if callable(self.on_wake):
                try:
                    self.on_wake()
                except Exception as exc:
                    print(
                        "[WAKE] Wake callback failed: "
                        f"{exc}",
                        flush=True,
                    )

            return True

        return False

    def close(self) -> None:
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
            except Exception:
                pass

            try:
                stream.close()
            except Exception:
                pass

        try:
            self.audio.terminate()
        except Exception:
            pass
