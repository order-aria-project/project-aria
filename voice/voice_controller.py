from __future__ import annotations

import threading
from typing import Callable, Optional

from .speech_listener import SpeechListener
from .wake_word_listener import WakeWordListener


class VoiceController:
    """
    Coordinates the wake-word and Whisper pipeline.
    """

    def __init__(
        self,
        command_callback: Callable[[str], object],
        wake_listener: WakeWordListener | None = None,
        speech_listener: SpeechListener | None = None,
    ) -> None:

        self.command_callback = command_callback

        self.wake_listener = (
            wake_listener
            or WakeWordListener()
        )

        self.speech_listener = (
            speech_listener
            or SpeechListener()
        )

        self.running = False
        self.stop_event = threading.Event()

    def start(self) -> None:

        if self.running:
            return

        self.running = True
        self.stop_event.clear()

        print(
            "[VOICE] Hands-free voice mode started.",
            flush=True,
        )

        print(
            "[VOICE] Say 'ARIA' to activate.",
            flush=True,
        )

        try:

            while (
                self.running
                and not self.stop_event.is_set()
            ):

                detected = (
                    self.wake_listener.listen_once()
                )

                if not self.running:
                    break

                if not detected:
                    continue

                print(
                    "[VOICE] Wake word accepted.",
                    flush=True,
                )

                self.wake_listener.pause()

                try:

                    if self.stop_event.is_set():
                        break

                    print(
                        "[VOICE] Listening "
                        "for command...",
                        flush=True,
                    )

                    command = (
                        self.speech_listener.listen_once()
                    )

                    if not command:

                        print(
                            "[VOICE] I didn't catch "
                            "a command.",
                            flush=True,
                        )

                        continue

                    print(
                        f"[VOICE] Command: {command}",
                        flush=True,
                    )

                    self.command_callback(
                        command
                    )

                finally:

                    if (
                        self.running
                        and not self.stop_event.is_set()
                    ):
                        try:
                            self.wake_listener.resume()
                        except Exception as exc:
                            print(
                                "[VOICE] Could not resume "
                                f"wake listener: {exc}",
                                flush=True,
                            )

        except KeyboardInterrupt:

            # Ctrl+C should be a normal shutdown,
            # not another error message.
            pass

        except Exception as exc:

            if self.running:

                print(
                    "[VOICE] Voice controller "
                    f"stopped because of: {exc}",
                    flush=True,
                )

        finally:

            self.stop()

    def process_once(
        self,
    ) -> Optional[str]:

        if self.stop_event.is_set():
            return None

        detected = (
            self.wake_listener.listen_once()
        )

        if not detected:
            return None

        self.wake_listener.pause()

        try:

            print(
                "[VOICE] Wake word accepted.",
                flush=True,
            )

            command = (
                self.speech_listener.listen_once()
            )

            if not command:

                print(
                    "[VOICE] No command detected.",
                    flush=True,
                )

                return None

            print(
                f"[VOICE] Command: {command}",
                flush=True,
            )

            self.command_callback(
                command
            )

            return command

        finally:

            if (
                self.running
                and not self.stop_event.is_set()
            ):
                self.wake_listener.resume()

    def stop(self) -> None:

        self.running = False
        self.stop_event.set()

        try:
            self.wake_listener.close()
        except Exception:
            pass

        try:
            self.speech_listener.close()
        except Exception:
            pass

        # Do not wait for the voice thread here.
        # It is a daemon thread and can exit naturally.