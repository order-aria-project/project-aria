from __future__ import annotations

import array
import math
import re
import struct
import tempfile
import wave
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Optional
import os
import json
import subprocess
import builtins
import threading
import time

_VERBOSE_VOICE_LOG = os.environ.get("ARIA_VERBOSE_VOICE", "0").strip() == "1"

def _voice_print(*args, **kwargs):
    if _VERBOSE_VOICE_LOG:
        builtins.print(*args, **kwargs)
        return
    text = " ".join(str(arg) for arg in args)
    important = (
        "Loading local Whisper model:",
        "Whisper CUDA mode active.",
        "Whisper CPU int8 mode active.",
        "[VOICE]",
        "[WAKE]",
    )
    if text.startswith(important):
        builtins.print(*args, **kwargs)

print = _voice_print


class _TDTTranscriptSegment:
    """Compatibility wrapper for the existing transcript-quality pipeline."""

    def __init__(self, text: str):
        self.text = text
        # TDT does not expose Whisper avg_logprob/compression metrics.
        # These conservative placeholders keep the existing quality pipeline
        # from rejecting valid TDT output without changing its logic elsewhere.
        self.avg_logprob = -0.45
        self.compression_ratio = 1.0

import pyaudio
from faster_whisper import WhisperModel

from .microphone_manager import MicrophoneManager


class SpeechListener:
    """
    High-confidence speech input for A.R.I.A.

    Design goals:
    - Use the locked ARIA microphone only.
    - Preserve the first and last words with audio pre-roll/pad.
    - Prefer CUDA when available, then fall back cleanly to CPU int8.
    - Decode with a stronger beam-search configuration than the original.
    - Reject clearly low-confidence/hallucinated transcripts rather than
      pretending ARIA understood them.
    - Apply only conservative, domain-specific transcript repairs.
    """

    KNOWN_APPS = (
        "brave",
        "chrome",
        "discord",
        "spotify",
        "blender",
        "roblox",
        "obs",
        "firefox",
        "edge",
        "steam",
        "notepad",
        "snipping tool",
        "task manager",
    )

    COMMAND_VOCABULARY = (
        "open, launch, start, close, quit, exit, mute, unmute, "
        "volume, audio, sound, system status, cpu, ram, memory, gpu, "
        "battery, disk, application, app, guest mode, aria mode, "
        "goodbye, stop, stop talking, be quiet"
    )

    # Strong, explicit request anchors. These are used only when a capture
    # also looks like singing/mixed audio, so ordinary conversational speech
    # keeps its original transcript.
    RECENT_INTENT_PATTERNS = (
        r"(?:what(?:'s| is)\s+the\s+time(?:\s+now)?)",
        r"(?:tell\s+me\s+the\s+time)",
        r"(?:what(?:'s| is)\s+the\s+date)",
        r"(?:what\s+date\s+is\s+it)",
        r"(?:what(?:'s| is)\s+the\s+date\s+and\s+time)",
        r"(?:what(?:'s| is)\s+the\s+current\s+date\s+and\s+time)",
        r"(?:open|launch|start)\s+.+",
        r"(?:close|quit|exit)\s+.+",
        r"(?:mute|unmute|restore)\s+.+",
    )

    def __init__(
        self,
        model_path: Path | None = None,
        microphone_manager: MicrophoneManager | None = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        max_listen_seconds: float = 12.0,
        silence_seconds: float = 1.30,
        minimum_speech_seconds: float = 0.18,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        self.microphone_manager = microphone_manager or MicrophoneManager()

        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.max_listen_seconds = max_listen_seconds
        self.silence_seconds = silence_seconds
        self.minimum_speech_seconds = minimum_speech_seconds
        self.should_stop = should_stop

        self.model_path = Path(
            model_path
            if model_path is not None
            else Path(__file__).resolve().parent / "model-whisper-small-en"
        )

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Whisper model folder not found: {self.model_path}"
            )

        print(
            "Loading Parakeet TDT V3 speech service...",
            flush=True,
        )

        self.asr_backend = "tdt"
        self.device_mode = "cuda"
        self.compute_type = "bfloat16"
        self.model = None
        self._tdt_process = None
        self._tdt_stdin = None
        self._tdt_stdout = None

        try:
            self._start_tdt_service()
            print("Parakeet TDT V3 speech service active.", flush=True)
        except Exception as exc:
            print(
                f"Parakeet TDT V3 unavailable; falling back to local Whisper. ({exc})",
                flush=True,
            )
            self._activate_whisper_fallback()

        self.audio = pyaudio.PyAudio()
        self._stream_lock = threading.RLock()
        self._stream_generation = 0

        self.active_device = self.microphone_manager.get_locked_device()

        # Lightweight acoustic profile from the most recent capture.
        # VoiceController uses this alongside the Whisper transcript to
        # distinguish sustained singing from normal spoken requests.
        self.last_audio_profile: dict[str, float | bool] = {}
        self.last_mean_logprob: float = -10.0
        self.last_compression_ratio: float = 0.0

        print(
            f"[VOICE] Locked microphone: {self.active_device.name} "
            f"(device index {self.active_device.index})",
            flush=True,
        )

    def _open_input(self):
        last_error = None
        for attempt in range(3):
            with self._stream_lock:
                try:
                    stream = self.audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=self.sample_rate,
                        input=True,
                        input_device_index=self.active_device.index,
                        frames_per_buffer=self.chunk_size,
                    )
                    self._stream_generation += 1
                    print(
                        f"[VOICE] Microphone stream opened "
                        f"(generation={self._stream_generation}, attempt={attempt + 1}).",
                        flush=True,
                    )
                    return stream
                except Exception as exc:
                    last_error = exc
                    print(
                        f"[VOICE] Microphone open failed "
                        f"(attempt {attempt + 1}/3): {exc}",
                        flush=True,
                    )
                    try:
                        self.audio.terminate()
                    except Exception:
                        pass
                    self.audio = pyaudio.PyAudio()
            time.sleep(0.15 * (attempt + 1))
        raise RuntimeError(
            f"Could not open locked microphone after 3 attempts: {last_error}"
        )

    @staticmethod
    def _calculate_rms(audio_data: bytes) -> float:
        if not audio_data:
            return 0.0

        sample_count = len(audio_data) // 2
        if sample_count <= 0:
            return 0.0

        samples = struct.unpack(f"<{sample_count}h", audio_data)
        total = sum(sample * sample for sample in samples)
        return (total / sample_count) ** 0.5

    @staticmethod
    def _normalise_audio(audio_data: bytes) -> bytes:
        samples = array.array("h")
        samples.frombytes(audio_data)

        if not samples:
            return audio_data

        peak = max(abs(sample) for sample in samples)
        if peak <= 0:
            return audio_data

        # Normalize only when clearly quiet/loud; avoid needless processing.
        target_peak = 24500.0
        gain = min(target_peak / float(peak), 3.0)

        if 0.88 <= gain <= 1.12:
            return audio_data

        output = array.array("h")
        for sample in samples:
            value = int(sample * gain)
            value = max(-32768, min(32767, value))
            output.append(value)

        return output.tobytes()

    @staticmethod
    def _frame_rms(samples: list[int]) -> float:
        if not samples:
            return 0.0
        total = sum(sample * sample for sample in samples)
        return math.sqrt(total / len(samples))

    @classmethod
    def _analyse_audio_profile(
        cls,
        audio_data: bytes,
        sample_rate: int,
    ) -> dict[str, float | bool]:
        """
        Estimate whether the captured utterance contains sustained,
        periodic voicing typical of singing.

        This is deliberately conservative and does not attempt speaker,
        language, or emotion classification.  It only supplies a few
        physical audio measurements to the VoiceController.
        """
        if not audio_data or sample_rate <= 0:
            return {
                "duration": 0.0,
                "voiced_ratio": 0.0,
                "pitch_ratio": 0.0,
                "pitch_stability": 0.0,
                "harmonicity": 0.0,
                "energy_variation": 1.0,
                "zcr_mean": 0.0,
                "zcr_variation": 0.0,
                "pitch_variability": 0.0,
                "pitch_direction_changes": 0.0,
                "speech_likeness": 0.0,
                "singing_score": 0.0,
                "likely_singing": False,
            }

        raw = array.array("h")
        raw.frombytes(audio_data)
        samples = list(raw)
        if not samples:
            return {
                "duration": 0.0,
                "voiced_ratio": 0.0,
                "pitch_ratio": 0.0,
                "pitch_stability": 0.0,
                "harmonicity": 0.0,
                "energy_variation": 1.0,
                "zcr_mean": 0.0,
                "zcr_variation": 0.0,
                "pitch_variability": 0.0,
                "pitch_direction_changes": 0.0,
                "speech_likeness": 0.0,
                "singing_score": 0.0,
                "likely_singing": False,
            }

        duration = len(samples) / float(sample_rate)
        frame_size = max(240, int(sample_rate * 0.030))
        hop = max(120, int(sample_rate * 0.015))

        if len(samples) < frame_size:
            return {
                "duration": duration,
                "voiced_ratio": 0.0,
                "pitch_ratio": 0.0,
                "pitch_stability": 0.0,
                "harmonicity": 0.0,
                "energy_variation": 1.0,
                "zcr_mean": 0.0,
                "zcr_variation": 0.0,
                "pitch_variability": 0.0,
                "pitch_direction_changes": 0.0,
                "speech_likeness": 0.0,
                "singing_score": 0.0,
                "likely_singing": False,
            }

        # Estimate a noise floor from the quietest short frames.
        rms_values: list[float] = []
        frames: list[list[int]] = []
        for start in range(0, len(samples) - frame_size + 1, hop):
            frame = samples[start:start + frame_size]
            rms = cls._frame_rms(frame)
            rms_values.append(rms)
            frames.append(frame)

        if not rms_values:
            return {
                "duration": duration,
                "voiced_ratio": 0.0,
                "pitch_ratio": 0.0,
                "pitch_stability": 0.0,
                "harmonicity": 0.0,
                "energy_variation": 1.0,
                "zcr_mean": 0.0,
                "zcr_variation": 0.0,
                "pitch_variability": 0.0,
                "pitch_direction_changes": 0.0,
                "speech_likeness": 0.0,
                "singing_score": 0.0,
                "likely_singing": False,
            }

        sorted_rms = sorted(rms_values)
        quiet_count = max(1, int(len(sorted_rms) * 0.15))
        low_level = sum(sorted_rms[:quiet_count]) / quiet_count
        median_rms = sorted_rms[len(sorted_rms) // 2]

        # When someone is singing continuously there may be no truly silent
        # frames inside the captured utterance. Cap the estimated noise floor
        # relative to the median so continuous voicing is not mistaken for
        # background noise.
        noise_floor = min(low_level, median_rms * 0.25)
        voiced_threshold = max(180.0, noise_floor * 1.55)
        voiced_threshold = min(
            voiced_threshold,
            max(180.0, median_rms * 0.55),
        )

        voiced_frames = [
            (frame, rms)
            for frame, rms in zip(frames, rms_values)
            if rms >= voiced_threshold
        ]
        voiced_ratio = len(voiced_frames) / max(1, len(frames))

        pitch_values: list[float] = []
        harmonic_values: list[float] = []

        # Human fundamentals in this broad range are enough for an acoustic
        # singing-vs-speech signal. Autocorrelation is used instead of any
        # external pitch package so this feature adds no dependency.

        decimation = 4
        reduced_rate = sample_rate / decimation

        for index, (frame, _rms) in enumerate(voiced_frames):
            # Every other voiced frame is enough for a coarse stability
            # estimate and keeps CPU use low on the Whisper CPU fallback.
            if index % 2:
                continue

            mean = sum(frame) / len(frame)
            reduced = []
            for offset in range(0, len(frame) - decimation + 1, decimation):
                reduced.append(
                    sum(frame[offset:offset + decimation]) / decimation
                    - mean
                )

            if len(reduced) < 32:
                continue

            energy = sum(sample * sample for sample in reduced)
            if energy <= 1.0:
                continue

            local_min_lag = max(2, int(reduced_rate / 420.0))
            local_max_lag = min(
                len(reduced) - 2,
                int(reduced_rate / 70.0),
            )

            best_corr = 0.0
            best_lag = None
            for lag in range(local_min_lag, local_max_lag + 1):
                a = reduced[:-lag]
                b = reduced[lag:]
                denom = math.sqrt(
                    sum(x * x for x in a) *
                    sum(y * y for y in b)
                )
                if denom <= 1.0:
                    continue
                corr = sum(x * y for x, y in zip(a, b)) / denom
                if corr > best_corr:
                    best_corr = corr
                    best_lag = lag

            if best_lag is not None and best_corr >= 0.28:
                pitch = reduced_rate / float(best_lag)
                if 70.0 <= pitch <= 420.0:
                    pitch_values.append(pitch)
                    harmonic_values.append(best_corr)

        pitch_ratio = len(pitch_values) / max(1, len(voiced_frames))
        harmonicity = (
            sum(harmonic_values) / len(harmonic_values)
            if harmonic_values
            else 0.0
        )

        pitch_variability = 0.0
        pitch_direction_changes = 0.0
        if len(pitch_values) >= 3:
            mean_pitch = sum(pitch_values) / len(pitch_values)
            if mean_pitch > 1.0:
                pitch_variability = min(1.0, math.sqrt(sum((value - mean_pitch) ** 2 for value in pitch_values) / len(pitch_values)) / mean_pitch * 3.0)
            directions = []
            for left, right in zip(pitch_values, pitch_values[1:]):
                if right > left * 1.03:
                    directions.append(1)
                elif right < left * 0.97:
                    directions.append(-1)
                else:
                    directions.append(0)
            non_zero = [value for value in directions if value]
            if len(non_zero) >= 2:
                changes = sum(1 for left, right in zip(non_zero, non_zero[1:]) if left != right)
                pitch_direction_changes = changes / max(1, len(non_zero) - 1)

        zcr_values = []
        for frame in frames:
            if not frame:
                continue
            crossings = 0
            previous = frame[0]
            for sample in frame[1:]:
                if (previous < 0 <= sample) or (previous >= 0 > sample):
                    crossings += 1
                previous = sample
            zcr_values.append(crossings / len(frame))

        zcr_mean = sum(zcr_values) / len(zcr_values) if zcr_values else 0.0
        zcr_variation = 0.0
        if len(zcr_values) >= 3 and zcr_mean > 0.0001:
            zcr_variation = min(1.0, math.sqrt(sum((value - zcr_mean) ** 2 for value in zcr_values) / len(zcr_values)) / zcr_mean * 2.4)

        pitch_stability = 0.0
        if len(pitch_values) >= 4:
            stable_pairs = 0
            total_pairs = 0
            for left, right in zip(pitch_values, pitch_values[1:]):
                if left <= 0 or right <= 0:
                    continue
                total_pairs += 1
                ratio = max(left, right) / min(left, right)
                if ratio <= 1.08:
                    stable_pairs += 1
            if total_pairs:
                pitch_stability = stable_pairs / total_pairs

        if rms_values:
            mean_rms = sum(rms_values) / len(rms_values)
            if mean_rms > 1.0:
                variance = sum(
                    (value - mean_rms) ** 2
                    for value in rms_values
                ) / len(rms_values)
                energy_variation = math.sqrt(variance) / mean_rms
            else:
                energy_variation = 1.0
        else:
            energy_variation = 1.0

        # Singing becomes much more likely when a long capture is mostly
        # voiced, strongly periodic, and has a stable fundamental. The
        # threshold is intentionally high: a false positive is worse than
        # allowing one ambiguous sentence through because explicit commands
        # still have higher priority in VoiceController.
        length_factor = min(1.0, max(0.0, (duration - 1.8) / 2.2))
        periodic_factor = min(1.0, harmonicity / 0.68)
        pitch_factor = min(1.0, pitch_ratio / 0.62)
        stability_factor = min(1.0, pitch_stability / 0.62)
        voiced_factor = min(1.0, voiced_ratio / 0.78)

        singing_score = (
            0.22 * length_factor
            + 0.20 * voiced_factor
            + 0.23 * periodic_factor
            + 0.23 * pitch_factor
            + 0.12 * stability_factor
        )

        # Avoid classifying short spoken phrases or highly intermittent speech
        # as singing merely because a few frames are periodic.
        speech_likeness = max(
            0.0,
            min(
                1.0,
                0.28 * min(1.0, energy_variation / 0.62)
                + 0.22 * zcr_variation
                + 0.22 * pitch_variability
                + 0.16 * pitch_direction_changes
                + 0.12 * (1.0 - min(1.0, harmonicity / 0.88))
            ),
        )

        likely_singing = (
            duration >= 2.4
            and voiced_ratio >= 0.68
            and pitch_ratio >= 0.42
            and harmonicity >= 0.50
            and singing_score >= 0.67
        )

        return {
            "duration": float(duration),
            "voiced_ratio": float(voiced_ratio),
            "pitch_ratio": float(pitch_ratio),
            "pitch_stability": float(pitch_stability),
            "harmonicity": float(harmonicity),
            "energy_variation": float(energy_variation),
            "zcr_mean": float(zcr_mean),
            "zcr_variation": float(zcr_variation),
            "pitch_variability": float(pitch_variability),
            "pitch_direction_changes": float(pitch_direction_changes),
            "speech_likeness": float(speech_likeness),
            "singing_score": float(singing_score),
            "likely_singing": bool(likely_singing),
        }

    def _write_temp_wav(self, audio_data: bytes) -> str:
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        )
        temp_path = temp_file.name
        temp_file.close()

        with wave.open(temp_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(
                self.audio.get_sample_size(pyaudio.paInt16)
            )
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_data)

        return temp_path

    @staticmethod
    def _normalise_text(text: str) -> str:
        text = str(text or "").lower().strip()
        text = text.replace("—", "-").replace("–", "-")
        text = re.sub(r"[^\w\s'-]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def _repair_common_semantic_mishearings(cls, text: str) -> str:
        """Conservative repairs for recurring speech-recognition errors."""
        normalized = cls._normalise_text(text)
        if not normalized:
            return normalized

        normalized = re.sub(
            r"\b(?:waltz|watts|walt|what is|what's)\s+"
            r"([0-9]+\s*(?:x|times|plus|minus|divided by|over)\s*[0-9]+"
            r"(?:\s*(?:x|times|plus|minus|divided by|over)\s*[0-9]+)*)\b",
            r"what's \1",
            normalized,
        )

        normalized = re.sub(
            r"\bwhat(?:'s| is)\s+the\s+(?:time|tim|tyme)\b",
            "what's the time",
            normalized,
        )

        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _repair_known_command_phrasing(cls, text: str) -> str:
        """
        Conservative repair layer.

        It must never invent an application name. It only repairs common
        speech forms where the intended command verb is unambiguous.
        """
        normalized = cls._normalise_text(text)

        if not normalized:
            return normalized

        # Common speech-recognition variants of "unmute".
        normalized = re.sub(
            r"\b(un[\s-]*mute|on\s+mute|take\s+off\s+mute|remove\s+mute)\b",
            "unmute",
            normalized,
        )

        # Common variants of "mute".
        normalized = re.sub(
            r"\b(muted?|mute\s+it)\b",
            "mute",
            normalized,
        )

        # Conservative repairs for observed short Whisper variants.
        if normalized in {
            "well its time",
            "well it is time",
            "what is the time",
            "whats time",
        }:
            normalized = "what's the time"

        normalized = re.sub(r"\s+", " ", normalized).strip()

        # Normalize known application names conservatively.
        words = normalized.split()
        if words:
            tail = words[-1]
            best_name = None
            best_score = 0.0

            for app in cls.KNOWN_APPS:
                score = SequenceMatcher(
                    None,
                    tail,
                    app,
                ).ratio()

                if score > best_score:
                    best_name = app
                    best_score = score

            # Only repair a single application token when it is genuinely
            # close to a known name. This avoids turning "phrase" into
            # "Brave", for example.
            if best_name and best_score >= 0.82 and tail != best_name:
                words[-1] = best_name
                normalized = " ".join(words)

        return normalized

    @classmethod
    def _repair_fuzzy_app_command(cls, text: str) -> str:
        """
        Targeted command-grammar rescue for short app commands.

        Parakeet can occasionally preserve the application name while
        mangling a short command verb. We only repair a structurally
        command-like utterance: a recognised verb alias followed by a
        known application (or a very close application spelling).
        """
        normalized = cls._normalise_text(text)
        if not normalized:
            return normalized

        words = normalized.split()
        if len(words) < 2 or len(words) > 6:
            return normalized

        # Observed variants from the user's microphone tests for
        # "close Roblox". Keep this intentionally narrow so ordinary
        # conversation is not rewritten.
        close_aliases = {
            "close",
            "clothes",
            "lows",
            "slow",
            "fellows",
            "pose",
            "blooms",
            "those",
            "flows",
        }
        open_aliases = {
            "open",
            "launch",
            "start",
        }
        quit_aliases = {
            "quit",
            "exit",
        }

        # Locate a known single-token application. Exact matches win;
        # otherwise allow a deliberately modest fuzzy match because
        # "roblox" -> "roadblocks" is a recurring observed error.
        app_aliases = {app: app for app in cls.KNOWN_APPS if " " not in app}
        app_index = None
        app_name = None
        app_score = 0.0

        for idx, token in enumerate(words):
            if token in app_aliases:
                app_index = idx
                app_name = app_aliases[token]
                app_score = 1.0
                break

            if len(token) < 5:
                continue

            for app in app_aliases:
                score = SequenceMatcher(None, token, app).ratio()
                if score > app_score:
                    app_index = idx
                    app_name = app
                    app_score = score

        if app_index is None or app_score < 0.60:
            return normalized

        # Only accept a command verb immediately before the app, allowing
        # a small amount of polite lead-in speech such as "please".
        before = [w for w in words[:app_index] if w not in {
            "please", "can", "could", "you", "aria", "the", "to",
            "as", "are", "is",
        }]
        if not before:
            return normalized

        action = None
        for verb in before:
            if verb in close_aliases or verb in quit_aliases:
                action = "close"
                break
            if verb in open_aliases:
                action = "open"
                break

        if action is None:
            return normalized

        repaired = f"{action} {app_name}"
        if repaired != normalized:
            print(
                "[VOICE] COMMAND GRAMMAR OVERRIDE: "
                f"{normalized!r} -> {repaired!r}",
                flush=True,
            )
        return repaired

    @classmethod
    def _quality_from_segments(
        cls,
        segments,
    ) -> tuple[str, float, float]:
        pieces: list[str] = []
        log_probs: list[float] = []
        compression_values: list[float] = []

        for segment in segments:
            text = str(getattr(segment, "text", "") or "").strip()

            if text:
                pieces.append(text)

            avg_logprob = getattr(segment, "avg_logprob", None)
            if avg_logprob is not None:
                try:
                    log_probs.append(float(avg_logprob))
                except (TypeError, ValueError):
                    pass

            compression_ratio = getattr(segment, "compression_ratio", None)
            if compression_ratio is not None:
                try:
                    compression_values.append(float(compression_ratio))
                except (TypeError, ValueError):
                    pass

        result = " ".join(pieces).strip()
        mean_logprob = (
            sum(log_probs) / len(log_probs)
            if log_probs
            else -10.0
        )
        max_compression = (
            max(compression_values)
            if compression_values
            else 0.0
        )

        return result, mean_logprob, max_compression

    def _start_tdt_service(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        service_path = Path(__file__).resolve().parent / "parakeet_tdt_service.py"
        python_path = Path(
            os.environ.get(
                "ARIA_TDT_PYTHON",
                project_root / ".parakeet_tdt_v3_venv" / "Scripts" / "python.exe",
            )
        )

        if not python_path.exists():
            raise FileNotFoundError(f"Parakeet TDT Python not found: {python_path}")
        if not service_path.exists():
            raise FileNotFoundError(f"Parakeet TDT service not found: {service_path}")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["HF_HUB_DISABLE_XET"] = "1"
        env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

        self._tdt_process = subprocess.Popen(
            [str(python_path), str(service_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
        )
        self._tdt_stdin = self._tdt_process.stdin
        self._tdt_stdout = self._tdt_process.stdout

        ready = self._tdt_stdout.readline().strip() if self._tdt_stdout else ""
        if ready != "READY":
            self._stop_tdt_service()
            raise RuntimeError(f"Unexpected Parakeet TDT service response: {ready!r}")

    def _stop_tdt_service(self) -> None:
        proc = self._tdt_process
        self._tdt_process = None
        self._tdt_stdin = None
        self._tdt_stdout = None

        if proc is None:
            return

        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _tdt_transcribe(self, wav_path: str):
        if (
            self._tdt_process is None
            or self._tdt_process.poll() is not None
            or self._tdt_stdin is None
            or self._tdt_stdout is None
        ):
            raise RuntimeError("Parakeet TDT service is not running.")

        self._tdt_stdin.write(json.dumps({"wav_path": str(wav_path)}) + "\n")
        self._tdt_stdin.flush()

        response_line = self._tdt_stdout.readline()
        if not response_line:
            raise RuntimeError("Parakeet TDT service closed its output.")

        response = json.loads(response_line)
        if not response.get("ok", False):
            raise RuntimeError(str(response.get("error", "Unknown TDT error")))

        return [
            _TDTTranscriptSegment(
                str(response.get("text", "") or "").strip()
            )
        ]

    def _activate_whisper_fallback(self) -> None:
        self.asr_backend = "whisper"
        self.device_mode = "cpu"
        self.compute_type = "int8"
        self.model = WhisperModel(
            str(self.model_path),
            device="cpu",
            compute_type="int8",
        )
        print("Whisper CPU int8 fallback active.", flush=True)

    def _switch_to_cpu_fallback(self, reason: Exception | str) -> None:
        """Switch Whisper to the proven local CPU int8 fallback."""
        if self.device_mode == "cpu":
            return

        print(
            "[VOICE] Switching Whisper to CPU fallback.",
            flush=True,
        )
        print(
            f"[VOICE] Reason: {reason}",
            flush=True,
        )
        print(
            "[VOICE] Loading CPU int8 Whisper fallback...",
            flush=True,
        )

        self.model = WhisperModel(
            str(self.model_path),
            device="cpu",
            compute_type="int8",
        )
        self.device_mode = "cpu"
        self.compute_type = "int8"

        print(
            "[VOICE] Whisper CPU int8 fallback ready.",
            flush=True,
        )

    def _transcribe_once(self, wav_path: str, initial_prompt: str):
        segments, _ = self.model.transcribe(
            wav_path,
            language="en",
            beam_size=8,
            best_of=8,
            patience=1.2,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 400,
                "speech_pad_ms": 450,
                "min_speech_duration_ms": 120,
            },
            no_speech_threshold=0.42,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.05,
            initial_prompt=initial_prompt,
            word_timestamps=False,
        )

        # faster-whisper returns a lazy generator. CUDA/CT2 errors can occur
        # only when that generator is consumed, which would otherwise bypass
        # the runtime fallback in _decode(). Materialise it here so the entire
        # inference is covered by the caller's try/except.
        return list(segments)

    def _decode_accuracy_pass(self, wav_path: str, initial_prompt: str):
        """Second-pass decode for short/suspicious command speech."""
        segments, _ = self.model.transcribe(
            wav_path,
            language="en",
            beam_size=10,
            best_of=10,
            patience=1.5,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 350,
                "speech_pad_ms": 500,
                "min_speech_duration_ms": 100,
            },
            no_speech_threshold=0.35,
            compression_ratio_threshold=2.8,
            log_prob_threshold=-1.15,
            initial_prompt=(
                initial_prompt
                + " Common spoken requests include arithmetic questions such as "
                  "\"what's two times two\", \"twenty times ninety\", and "
                  "time/date questions. Preserve the words actually spoken."
            ),
            word_timestamps=False,
        )
        return list(segments)

    def _decode(self, wav_path: str, initial_prompt: str):
        if self.asr_backend == "tdt":
            try:
                return self._tdt_transcribe(wav_path)
            except Exception as exc:
                print(
                    f"[VOICE] Parakeet TDT failed; switching to Whisper fallback. ({exc})",
                    flush=True,
                )
                self._stop_tdt_service()
                self._activate_whisper_fallback()

        try:
            return self._transcribe_once(wav_path, initial_prompt)
        except Exception as exc:
            message = str(exc).lower()
            cuda_failure = (
                self.device_mode == "cuda"
                and (
                    "cublas" in message
                    or "cuda" in message
                    or "cudnn" in message
                    or "ctranslate2" in message
                    or "dll" in message
                    or "cannot be loaded" in message
                    or "not found" in message
                )
            )

            if not cuda_failure:
                raise

            self._switch_to_cpu_fallback(exc)
            return self._transcribe_once(wav_path, initial_prompt)

    def verify_wake_word(self, audio_data: bytes) -> bool:
        """
        Strict second-pass verification for exactly one word: ARIA.
        """
        if not audio_data:
            return False

        wav_path = None

        try:
            wav_path = self._write_temp_wav(audio_data)

            segments = self._decode(
                wav_path,
                (
                    "The wake word is ARIA. "
                    "Only return the words actually spoken."
                ),
            )

            result, mean_logprob, _ = self._quality_from_segments(segments)
            normalized = self._normalise_text(result)

            print(
                f"[WAKE] Whisper heard: {normalized!r} "
                f"(logprob={mean_logprob:.2f})",
                flush=True,
            )

            return (
                normalized == "aria"
                and mean_logprob >= -1.25
            )

        except Exception as exc:
            print(
                f"[WAKE] Wake verification error: {exc}",
                flush=True,
            )
            return False

        finally:
            if wav_path is not None:
                try:
                    Path(wav_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _record_audio(self) -> Optional[bytes]:
        stream = None

        try:
            print("[VOICE] CAPTURE ENGINE ARMED — waiting for voice...", flush=True)
            stream = self._open_input()

            print(
                f"[VOICE] Listening through: {self.active_device.name}",
                flush=True,
            )
            print("[VOICE] Speak now...", flush=True)

            frame_duration = self.chunk_size / self.sample_rate
            max_frames = max(
                1,
                int(self.max_listen_seconds / frame_duration),
            )

            silence_frames_required = max(
                1,
                int(self.silence_seconds / frame_duration),
            )

            minimum_speech_frames = max(
                1,
                int(self.minimum_speech_seconds / frame_duration),
            )

            calibration_frames = max(
                1,
                int(0.18 / frame_duration),
            )

            calibration_levels: list[float] = []

            for _ in range(calibration_frames):
                if self.should_stop is not None and self.should_stop():
                    return None

                data = stream.read(
                    self.chunk_size,
                    exception_on_overflow=False,
                )
                calibration_levels.append(self._calculate_rms(data))

            if calibration_levels:
                calibration_levels.sort()
                quiet_count = max(
                    1,
                    int(len(calibration_levels) * 0.70),
                )
                noise_floor = (
                    sum(calibration_levels[:quiet_count])
                    / quiet_count
                )
            else:
                noise_floor = 0.0

            # Hysteresis VAD: a slightly easier start threshold preserves quiet
            # first words, while a lower continuation threshold keeps the phrase
            # intact through normal consonant gaps and soft endings.
            speech_start_threshold = max(
                85.0,
                noise_floor * 1.05,
            )
            speech_continue_threshold = max(
                65.0,
                noise_floor * 0.78,
            )

            frames: list[bytes] = []
            pre_roll: list[bytes] = []

            pre_roll_limit = max(
                1,
                int(0.75 / frame_duration),
            )

            speech_started = False
            speech_frame_count = 0
            speech_candidate_frames = 0
            silence_frame_count = 0

            # Two consecutive candidate frames avoids triggering on a single
            # click/pop but still starts quickly enough for short requests.
            speech_start_debounce = 2

            for _ in range(max_frames):
                if self.should_stop is not None and self.should_stop():
                    return None

                data = stream.read(
                    self.chunk_size,
                    exception_on_overflow=False,
                )

                pre_roll.append(data)
                if len(pre_roll) > pre_roll_limit:
                    pre_roll.pop(0)

                rms = self._calculate_rms(data)

                if not speech_started:
                    if rms >= speech_start_threshold:
                        speech_candidate_frames += 1
                    else:
                        speech_candidate_frames = 0

                    if speech_candidate_frames >= speech_start_debounce:
                        frames.extend(pre_roll)
                        speech_started = True
                        speech_frame_count = speech_candidate_frames
                        silence_frame_count = 0
                        frames.append(data)

                else:
                    is_continuation = rms >= speech_continue_threshold

                    if is_continuation:
                        speech_frame_count += 1
                        silence_frame_count = 0
                    else:
                        silence_frame_count += 1

                    frames.append(data)

                    if (
                        speech_frame_count >= minimum_speech_frames
                        and silence_frame_count >= silence_frames_required
                    ):
                        break

            if not frames:
                return None

            raw_audio = b"".join(frames)
            duration = len(raw_audio) / (self.sample_rate * 2)

            if duration < 0.30:
                return None

            print(
                f"[VOICE] INPUT CAPTURED — {duration:.2f}s; "
                "silence boundary reached.",
                flush=True,
            )

            self.last_audio_profile = self._analyse_audio_profile(
                raw_audio,
                self.sample_rate,
            )

            profile = self.last_audio_profile
            print(
                "[VOICE] ACOUSTIC: "
                f"singing={profile.get('singing_score', 0.0):.2f} "
                f"speech={profile.get('speech_likeness', 0.0):.2f} "
                f"pitch={profile.get('pitch_ratio', 0.0):.2f} "
                f"harmonic={profile.get('harmonicity', 0.0):.2f} "
                f"stable={profile.get('pitch_stability', 0.0):.2f} "
                f"likely_singing={profile.get('likely_singing', False)}",
                flush=True,
            )

            return self._normalise_audio(raw_audio)

        except Exception as exc:
            print(
                f"[VOICE] Could not use {self.active_device.name}: {exc}",
                flush=True,
            )
            return None

        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                except Exception:
                    pass

                try:
                    stream.close()
                except Exception:
                    pass

    @classmethod
    def _prefer_recent_explicit_intent(
        cls,
        transcript: str,
        profile: dict[str, float | bool],
    ) -> str:
        """Prefer a strong final spoken command over preceding singing.

        This is intentionally conservative: it only rewrites a transcript when
        the capture shows substantial singing/melodic content AND a strong,
        explicit command/question appears later in the same transcript.
        """
        normalized = cls._normalise_text(transcript)
        if not normalized:
            return normalized

        singing_score = float(profile.get("singing_score", 0.0) or 0.0)
        likely_singing = bool(profile.get("likely_singing", False))
        if not likely_singing and singing_score < 0.62:
            return normalized

        lowered = normalized.lower()
        candidates: list[tuple[int, str]] = []

        for pattern in cls.RECENT_INTENT_PATTERNS:
            for match in re.finditer(pattern, lowered):
                phrase = match.group(0).strip()
                candidates.append((match.start(), phrase))

        if not candidates:
            return normalized

        # Latest explicit request wins.
        _, phrase = max(candidates, key=lambda item: item[0])
        phrase = phrase.strip()

        # Preserve the original casing/normalisation conventions.
        return phrase

    @staticmethod
    def _final_confidence(
        logprob: float,
        compression: float,
        speech_likeness: float,
        singing_score: float,
        duration: float,
        transcript: str,
    ) -> float:
        logprob_score = max(0.0, min(1.0, (logprob + 1.40) / 1.20))
        compression_score = 1.0 - max(
            0.0, min(1.0, max(0.0, compression - 1.0) / 1.50)
        )
        duration_score = 1.0 if duration >= 0.45 else max(0.0, duration / 0.45)
        transcript_score = 1.0 if transcript.strip() else 0.0
        value = (
            0.42 * logprob_score
            + 0.20 * compression_score
            + 0.20 * max(0.0, min(1.0, speech_likeness))
            + 0.08 * (1.0 - max(0.0, min(1.0, singing_score)))
            + 0.05 * duration_score
            + 0.05 * transcript_score
        )
        return max(0.0, min(1.0, value))

    def _transcribe(self, wav_path: str) -> Optional[str]:
        print("[VOICE] Transcribing...", flush=True)

        initial_prompt = (
            "The user is speaking to a personal Windows desktop assistant. "
            "They may issue commands or ask questions. "
            f"Known applications: {', '.join(self.KNOWN_APPS)}. "
            f"Common command vocabulary: {self.COMMAND_VOCABULARY}. "
            "Common natural requests include arithmetic, time, date, system status, "
            "open/close/mute/unmute commands, and ordinary conversation. "
            "Return only what the user actually said."
        )

        segments = self._decode(
            wav_path,
            initial_prompt,
        )

        result, mean_logprob, max_compression = (
            self._quality_from_segments(segments)
        )
        self.last_mean_logprob = float(mean_logprob)
        self.last_compression_ratio = float(max_compression)

        normalized_first = self._normalise_text(result)
        has_math_shape = bool(
            re.search(
                r"\b\d+\s*(?:x|times|plus|minus|divided by|over)\s*\d+\b",
                normalized_first,
            )
        )
        suspicious_words = {"waltz", "watts", "walt"}
        needs_accuracy_pass = (
            len(normalized_first.split()) <= 8
            and (
                has_math_shape
                or any(word in suspicious_words for word in normalized_first.split())
            )
        )

        if needs_accuracy_pass and self.asr_backend == "whisper":
            try:
                retry_segments = self._decode_accuracy_pass(
                    wav_path,
                    initial_prompt,
                )
                retry_result, retry_logprob, retry_compression = (
                    self._quality_from_segments(retry_segments)
                )

                if retry_result and retry_logprob >= mean_logprob - 0.15:
                    result = retry_result
                    mean_logprob = retry_logprob
                    max_compression = retry_compression
                    self.last_mean_logprob = float(mean_logprob)
                    self.last_compression_ratio = float(max_compression)
                    print("[VOICE] Accuracy pass selected.", flush=True)
            except Exception as exc:
                print(f"[VOICE] Accuracy pass skipped: {exc}", flush=True)

        result = self._repair_common_semantic_mishearings(result)

        if not result:
            return None

        if mean_logprob < -1.20:
            print(
                f"[VOICE] Transcript rejected: low confidence "
                f"(logprob={mean_logprob:.2f}).",
                flush=True,
            )
            return None

        if max_compression > 2.6:
            print(
                f"[VOICE] Transcript rejected: likely hallucination "
                f"(compression={max_compression:.2f}).",
                flush=True,
            )
            return None

        profile = self.last_audio_profile
        singing_score = float(
            profile.get("singing_score", 0.0) or 0.0
        )
        speech_likeness = float(
            profile.get("speech_likeness", 0.0) or 0.0
        )
        pitch_ratio = float(
            profile.get("pitch_ratio", 0.0) or 0.0
        )
        harmonicity = float(
            profile.get("harmonicity", 0.0) or 0.0
        )
        likely_singing = bool(
            profile.get("likely_singing", False)
        )
        duration = float(
            profile.get("duration", 0.0) or 0.0
        )

        confidence = self._final_confidence(
            logprob=mean_logprob,
            compression=max_compression,
            speech_likeness=speech_likeness,
            singing_score=singing_score,
            duration=duration,
            transcript=result,
        )
        self.last_final_confidence = confidence

        print(
            "[VOICE] INPUT QUALITY: "
            f"logprob={mean_logprob:.2f} "
            f"compression={max_compression:.2f} "
            f"duration={duration:.2f}s "
            f"singing={singing_score:.2f} "
            f"speech={speech_likeness:.2f} "
            f"pitch={pitch_ratio:.2f} "
            f"harmonic={harmonicity:.2f} "
            f"likely_singing={likely_singing}",
            flush=True,
        )

        recent_intent = self._prefer_recent_explicit_intent(
            result,
            profile,
        )
        if recent_intent != self._normalise_text(result):
            print(
                "[VOICE] RECENT INTENT OVERRIDE: "
                f"{result!r} -> {recent_intent!r}",
                flush=True,
            )
            result = recent_intent

        repaired = self._repair_known_command_phrasing(result)
        repaired = self._repair_fuzzy_app_command(repaired)

        print(
            f"[VOICE] FINAL CONFIDENCE: {confidence:.3f} "
            f"logprob={mean_logprob:.2f} "
            f"compression={max_compression:.2f}",
            flush=True,
        )

        if repaired != self._normalise_text(result):
            print(
                f"[VOICE] Transcript repair: "
                f"{result!r} -> {repaired!r}",
                flush=True,
            )

        print(
            f"[VOICE] FINAL COMMAND: {repaired!r}",
            flush=True,
        )

        return repaired or None

    def listen_once(self) -> Optional[str]:
        self.last_audio_profile = {}
        self.last_mean_logprob = -10.0
        self.last_compression_ratio = 0.0
        self.last_final_confidence = 0.0

        print(
            "[VOICE] READY — your turn. Speak now.",
            flush=True,
        )

        audio_data = self._record_audio()

        if not audio_data:
            return None

        wav_path = None

        try:
            wav_path = self._write_temp_wav(audio_data)
            return self._transcribe(wav_path)

        except Exception as exc:
            print(
                f"[VOICE] Transcription failed: {exc}",
                flush=True,
            )
            return None

        finally:
            if wav_path is not None:
                try:
                    Path(wav_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def close(self) -> None:
        self._stop_tdt_service()
        try:
            self.audio.terminate()
        except Exception:
            pass
