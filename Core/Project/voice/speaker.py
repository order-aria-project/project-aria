from __future__ import annotations

import subprocess
import threading
from typing import Optional


class VoiceSpeaker:
    """Offline Windows speech using built-in SAPI with true global barge-in."""

    _active_process: Optional[subprocess.Popen] = None
    _lock = threading.RLock()

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            process = self._process
            return process is not None and process.poll() is None

    @classmethod
    def _register_process(cls, process: subprocess.Popen) -> None:
        with cls._lock:
            cls._active_process = process

    @classmethod
    def _clear_process(cls, process: Optional[subprocess.Popen]) -> None:
        with cls._lock:
            if cls._active_process is process:
                cls._active_process = None

    @classmethod
    def stop_active(cls) -> None:
        """
        Compatibility entry point used by InterruptListener.

        InterruptListener intentionally calls this on the class so a
        short-lived Vosk listener can stop whichever ARIA speaker instance
        is currently talking.
        """
        with cls._lock:
            process = cls._active_process

        if process is None:
            return

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.75)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception:
            pass
        finally:
            cls._clear_process(process)

    def speak(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return

        escaped = (
            text
            .replace("'", "''")
            .replace("\r", " ")
            .replace("\n", " ")
        )

        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Speak('"
            + escaped
            + "'); "
            "$s.Dispose()"
        )

        process: Optional[subprocess.Popen] = None

        try:
            process = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    command,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            with self._lock:
                self._process = process

            self._register_process(process)
            process.wait()

        except Exception as exc:
            print(
                f"[VOICE] TTS failed: {exc}",
                flush=True,
            )

        finally:
            self._clear_process(process)
            with self._lock:
                if self._process is process:
                    self._process = None

    def stop(self) -> None:
        """Stop this speaker instance's active SAPI process."""
        with self._lock:
            process = self._process

        if process is None:
            return

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.75)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception:
            pass
        finally:
            self._clear_process(process)
            with self._lock:
                if self._process is process:
                    self._process = None
