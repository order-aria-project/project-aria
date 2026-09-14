from __future__ import annotations

import struct
import tempfile
import time
import wave
from pathlib import Path
from typing import Optional

import pyaudio
from faster_whisper import WhisperModel

from .microphone_manager import (
    MicrophoneDevice,
    MicrophoneManager,
)


class SpeechListener:
    """
    Local speech recognition using faster-whisper.

    Phase 1:
    - Manual voice commands
    - Local Whisper model
    - CPU transcription
    - BlackShark microphone preferred
    - Laptop microphone fallback
    - Automatic stop after silence
    - No wake word yet
    - No always-listening yet
    """

    def __init__(
        self,
        model_path: Path | None = None,
        microphone_manager: MicrophoneManager | None = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        max_listen_seconds: float = 6.0,
        silence_seconds: float = 0.65,
        minimum_speech_seconds: float = 0.25,
    ) -> None:
        self.microphone_manager = (
            microphone_manager
            or MicrophoneManager()
        )

        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.max_listen_seconds = max_listen_seconds
        self.silence_seconds = silence_seconds
        self.minimum_speech_seconds = (
            minimum_speech_seconds
        )

        if model_path is None:
            model_path = (
                Path(__file__).resolve().parent
                / "model-whisper-small-en"
            )

        self.model_path = Path(model_path)

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Whisper model folder not found: "
                f"{self.model_path}"
            )

        print(
            f"Loading local Whisper model:\n"
            f"{self.model_path}",
            flush=True,
        )

        self.model = WhisperModel(
            str(self.model_path),
            device="cpu",
            compute_type="int8",
        )

        print(
            "Whisper CPU mode active.",
            flush=True,
        )

        self.audio = pyaudio.PyAudio()

    def _open_input(
        self,
        device_index: int,
    ):
        return self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.chunk_size,
        )

    def _calculate_rms(
        self,
        audio_data: bytes,
    ) -> float:
        if not audio_data:
            return 0.0

        sample_count = len(audio_data) // 2

        if sample_count <= 0:
            return 0.0

        samples = struct.unpack(
            f"<{sample_count}h",
            audio_data,
        )

        total = sum(
            sample * sample
            for sample in samples
        )

        return (
            total / sample_count
        ) ** 0.5

    def _record_audio(
        self,
        device: MicrophoneDevice,
    ) -> Optional[bytes]:

        stream = None

        try:
            stream = self._open_input(
                device.index
            )

            print(
                f"[VOICE] Listening through: "
                f"{device.name}",
                flush=True,
            )

            print(
                "[VOICE] Speak now...",
                flush=True,
            )

            frame_duration = (
                self.chunk_size
                / self.sample_rate
            )

            max_frames = int(
                self.max_listen_seconds
                / frame_duration
            )

            silence_frames_required = max(
                1,
                int(
                    self.silence_seconds
                    / frame_duration
                ),
            )

            minimum_speech_frames = max(
                1,
                int(
                    self.minimum_speech_seconds
                    / frame_duration
                ),
            )

            # Capture a short noise sample first.
            calibration_frames = max(
                1,
                int(0.25 / frame_duration),
            )

            calibration_levels = []

            for _ in range(calibration_frames):
                data = stream.read(
                    self.chunk_size,
                    exception_on_overflow=False,
                )

                calibration_levels.append(
                    self._calculate_rms(data)
                )

            noise_floor = (
                sum(calibration_levels)
                / len(calibration_levels)
            )

            # Dynamic threshold based on microphone noise.
            speech_threshold = max(
                450.0,
                noise_floor * 2.5,
            )

            frames: list[bytes] = []

            speech_started = False
            speech_frame_count = 0
            silence_frame_count = 0

            for _ in range(max_frames):
                data = stream.read(
                    self.chunk_size,
                    exception_on_overflow=False,
                )

                rms = self._calculate_rms(
                    data
                )

                is_speech = (
                    rms >= speech_threshold
                )

                if is_speech:
                    speech_started = True
                    speech_frame_count += 1
                    silence_frame_count = 0
                    frames.append(data)

                elif speech_started:
                    frames.append(data)
                    silence_frame_count += 1

                    if (
                        speech_frame_count
                        >= minimum_speech_frames
                        and silence_frame_count
                        >= silence_frames_required
                    ):
                        break

            if not frames:
                return None

            return b"".join(frames)

        except Exception as exc:
            print(
                f"[VOICE] Could not use "
                f"{device.name}: {exc}",
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

    def _write_temp_wav(
        self,
        audio_data: bytes,
    ) -> str:

        temp_file = tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        )

        temp_path = temp_file.name
        temp_file.close()

        with wave.open(
            temp_path,
            "wb",
        ) as wav_file:

            wav_file.setnchannels(1)

            wav_file.setsampwidth(
                self.audio.get_sample_size(
                    pyaudio.paInt16
                )
            )

            wav_file.setframerate(
                self.sample_rate
            )

            wav_file.writeframes(
                audio_data
            )

        return temp_path

    def _transcribe(
        self,
        wav_path: str,
    ) -> Optional[str]:

        print(
            "[VOICE] Transcribing...",
            flush=True,
        )

        segments, _ = self.model.transcribe(
            wav_path,
            language="en",
            beam_size=3,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
        )

        pieces: list[str] = []

        for segment in segments:
            text = segment.text.strip()

            if text:
                pieces.append(text)

        result = " ".join(
            pieces
        ).strip()

        if not result:
            return None

        return result

    def _get_candidate_devices(
        self,
    ) -> list[MicrophoneDevice]:

        devices: list[
            MicrophoneDevice
        ] = []

        preferred = (
            self.microphone_manager
            .find_preferred_device()
        )

        fallback = (
            self.microphone_manager
            .find_laptop_device()
        )

        if preferred is not None:
            devices.append(preferred)

        if (
            fallback is not None
            and (
                preferred is None
                or fallback.index
                != preferred.index
            )
        ):
            devices.append(fallback)

        return devices

    def listen_once(
        self,
    ) -> Optional[str]:

        devices = (
            self._get_candidate_devices()
        )

        if not devices:
            raise RuntimeError(
                "ARIA could not find a usable microphone."
            )

        for device in devices:

            audio_data = self._record_audio(
                device
            )

            if not audio_data:
                continue

            wav_path = None

            try:
                wav_path = (
                    self._write_temp_wav(
                        audio_data
                    )
                )

                result = self._transcribe(
                    wav_path
                )

                if result:
                    return result

            except Exception as exc:
                print(
                    "[VOICE] Transcription failed:",
                    exc,
                    flush=True,
                )

            finally:
                if wav_path is not None:
                    try:
                        Path(
                            wav_path
                        ).unlink(
                            missing_ok=True
                        )
                    except Exception:
                        pass

        return None

    def close(self) -> None:
        try:
            self.audio.terminate()
        except Exception:
            pass