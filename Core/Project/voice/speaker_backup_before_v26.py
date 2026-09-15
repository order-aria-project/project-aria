from __future__ import annotations

import subprocess
import threading
from typing import Optional


class VoiceSpeaker:
    """
    Offline Windows SAPI speech.

    A single class-level process reference allows the interruption
    listener to terminate the currently speaking response.
    """

    _active_process: Optional[
        subprocess.Popen
    ] = None

    _lock = threading.Lock()

    _stop_requested = False

    @classmethod
    def stop_active(cls) -> None:
        """
        Forcefully terminate the active PowerShell/SAPI process.

        taskkill /T /F is used because SAPI runs underneath the
        PowerShell process and a normal terminate() is not always
        sufficient to stop the complete speech chain immediately.
        """

        with cls._lock:
            process = cls._active_process

            if process is None:
                return

            cls._stop_requested = True

        try:
            if process.poll() is None:
                try:
                    subprocess.run(
                        [
                            "taskkill",
                            "/PID",
                            str(process.pid),
                            "/T",
                            "/F",
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        check=False,
                    )
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass

        except Exception:
            pass

    def speak(
        self,
        text: str,
    ) -> None:
        text = text.strip()

        if not text:
            return

        escaped = (
            text
            .replace(
                "'",
                "''",
            )
            .replace(
                "\r",
                " ",
            )
            .replace(
                "\n",
                " ",
            )
        )

        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object "
            "System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Speak('"
            + escaped
            + "'); "
            "$s.Dispose()"
        )

        process = None

        with self._lock:
            self.__class__._stop_requested = False

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
                self.__class__._active_process = process

            print(
                "[VOICE] Speaking...",
                flush=True,
            )

            process.wait()

        except Exception as exc:
            print(
                f"[VOICE] TTS error: {exc}",
                flush=True,
            )

        finally:
            with self._lock:
                interrupted = (
                    self.__class__._stop_requested
                )

                if (
                    self.__class__._active_process
                    is process
                ):
                    self.__class__._active_process = None

                self.__class__._stop_requested = False

            if interrupted:
                print(
                    "[VOICE] Speech interrupted.",
                    flush=True,
                )
            else:
                print(
                    "[VOICE] Speech complete.",
                    flush=True,
                )

    def stop(self) -> None:
        self.stop_active()