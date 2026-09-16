from __future__ import annotations

import subprocess
import threading
from typing import Optional


class VoiceSpeaker:
    """Offline Windows speech using built-in SAPI, with true barge-in stop."""

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            process = self._process
            return process is not None and process.poll() is None

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

            process.wait()

        except Exception as exc:
            print(f"[VOICE] TTS failed: {exc}", flush=True)

        finally:
            with self._lock:
                if self._process is process:
                    self._process = None

    def stop(self) -> None:
        """Immediately stop active SAPI speech; safe from another thread."""
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
            with self._lock:
                if self._process is process:
                    self._process = None
