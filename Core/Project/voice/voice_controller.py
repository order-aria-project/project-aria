from __future__ import annotations

import inspect
import random
import re
import threading
import time
from typing import Callable, Optional

try:
    from resemblyzer import SetLogLevel
except Exception:
    SetLogLevel = None

from voice.interrupt_listener import InterruptListener
from voice.speaker import VoiceSpeaker
from voice.wake_word_listener import WakeWordListener


class VoiceController:
    """
    ARIA voice-state controller.

    NORMAL MODE:
        Say ARIA once.
        ARIA acknowledges.
        Speak commands normally.
        ARIA remains conversational and does NOT require
        the wake word again.

    GUEST MODE:
        Guest Mode remains active until explicitly exited.
        Every guest interaction requires the ARIA wake word.
        After one guest interaction, ARIA returns to waiting
        for the next wake word.

    IMPORTANT:
        State-changing commands such as Guest Mode are handled
        here before the AI receives the command. This prevents
        the AI from merely saying it changed state without
        actually changing the controller state.
    """

    STATE_IDLE = "idle"
    STATE_ACTIVE = "active"
    STATE_GUEST = "guest"

    WAKE_RESPONSES = (
        "Yes, Beau?",
        "Yeah?",
        "What's up?",
        "I'm here.",
        "Go ahead.",
    )

    # ------------------------------------------------------------------
    # START / STOP WORDS
    # ------------------------------------------------------------------

    CONVERSATION_END_PHRASES = {
        "goodbye",
        "bye",
        "bye aria",
        "thats all",
        "that's all",
        "go idle",
        "stand by",
        "standby",
        "stop listening",
        "end conversation",
        "end this conversation",
    }

    # ------------------------------------------------------------------
    # CONSTRUCTOR
    # ------------------------------------------------------------------

    def __init__(
        self,
        command_callback: Callable[[str], Optional[str]],
        speech_listener,
        conversation_timeout: float = 0.0,
    ) -> None:

        if SetLogLevel is not None:
            try:
                SetLogLevel(-1)
            except Exception:
                pass

        self.command_callback = command_callback
        self.speech_listener = speech_listener

        # 0 = no inactivity timeout.
        self.conversation_timeout = float(
            conversation_timeout or 0.0
        )

        self.speaker = VoiceSpeaker()

        self.running = False

        self._thread: Optional[
            threading.Thread
        ] = None

        self._stop_event = threading.Event()

        self.state = self.STATE_IDLE

        self.last_interaction = 0.0

        # After background/singing speech is rejected, briefly enter a
        # recovery state so the next real user request can break through.
        self._attention_recovery = False

        self._barge_listener = None
        self._last_interrupt_time = 0.0
        self._mic_handoff_delay = 0.22

        self._wake_listener = (
            self._create_wake_listener()
        )

        self._create_barge_listener()

        if hasattr(
            self.speech_listener,
            "should_stop",
        ):
            self.speech_listener.should_stop = (
                self._stop_event.is_set
            )

    # ==================================================================
    # WAKE LISTENER
    # ==================================================================

    def _create_wake_listener(self):

        signature = inspect.signature(
            WakeWordListener
        )

        parameters = signature.parameters
        kwargs = {}

        verifier = getattr(
            self.speech_listener,
            "verify_wake_word",
            None,
        )

        if (
            "verify_callback" in parameters
            and callable(verifier)
        ):
            kwargs[
                "verify_callback"
            ] = verifier

        if "on_wake" in parameters:
            kwargs[
                "on_wake"
            ] = self._on_wake_detected

        listener = WakeWordListener(
            **kwargs
        )

        print(
            "[WAKE] Listener ready.",
            flush=True,
        )

        return listener

    def _on_wake_detected(
        self,
        *args,
        **kwargs,
    ) -> None:

        if self.running:
            print(
                "[WAKE] Verified.",
                flush=True,
            )

    # ==================================================================
    # BARGE / INTERRUPTION
    # ==================================================================

    def _create_barge_listener(self) -> None:

        try:

            self._barge_listener = (
                InterruptListener(
                    microphone_manager=getattr(
                        self.speech_listener,
                        "microphone_manager",
                        None,
                    ),
                    sample_rate=getattr(
                        self.speech_listener,
                        "sample_rate",
                        16000,
                    ),
                    chunk_size=getattr(
                        self.speech_listener,
                        "chunk_size",
                        1024,
                    ),
                    shared_audio=getattr(
                        self.speech_listener,
                        "audio",
                        None,
                    ),
                    shared_device=getattr(
                        self.speech_listener,
                        "active_device",
                        None,
                    ),
                    on_interrupt=(
                        self._handle_interrupt
                    ),
                )
            )

            print(
                "[BARGE] System ready.",
                flush=True,
            )

        except Exception as exc:

            self._barge_listener = None

            print(
                f"[BARGE] Setup failed: {exc}",
                flush=True,
            )

    def _start_barge_listener(self) -> None:

        if self._barge_listener is None:
            return

        try:
            self._barge_listener.start()
        except Exception as exc:
            print(
                f"[BARGE] Start failed: {exc}",
                flush=True,
            )

    def _stop_barge_listener(self) -> None:

        if self._barge_listener is None:
            return

        try:
            self._barge_listener.stop()
        except Exception:
            pass

    def _handle_interrupt(self) -> None:

        self._last_interrupt_time = time.monotonic()
        print(
            "[BARGE] Interruption accepted; taking the floor.",
            flush=True,
        )

        # True Jarvis-style barge-in: Vosk does not merely flag the
        # interruption; it immediately stops the active SAPI process.
        try:
            self.speaker.stop()
        except Exception as exc:
            print(
                f"[BARGE] TTS stop failed: {exc}",
                flush=True,
            )

        self._attention_recovery = True

    # ==================================================================
    # SPEAKING
    # ==================================================================

    def _say(
        self,
        text: str,
    ) -> None:

        if (
            not text
            or self._stop_event.is_set()
        ):
            return

        print(
            "[VOICE] Speaking...",
            flush=True,
        )

        self._start_barge_listener()

        try:

            self.speaker.speak(
                text
            )

        except Exception as exc:

            print(
                f"[VOICE] Speech error: {exc}",
                flush=True,
            )

        finally:

            self._stop_barge_listener()

            # A real interruption must hand the floor back immediately.
            if not self._stop_event.is_set() and self._last_interrupt_time:
                elapsed = time.monotonic() - self._last_interrupt_time
                if elapsed < self._mic_handoff_delay:
                    time.sleep(
                        self._mic_handoff_delay - elapsed
                    )
            elif not self._stop_event.is_set():
                time.sleep(self._mic_handoff_delay)

    def _say_wake_response(self) -> None:

        self._say(
            random.choice(
                self.WAKE_RESPONSES
            )
        )

    # ==================================================================
    # STATE
    # ==================================================================

    def _set_state(
        self,
        new_state: str,
    ) -> None:

        if self.state == new_state:
            return

        old_state = self.state

        self.state = new_state

        print(
            f"[VOICE] "
            f"{old_state.upper()} -> "
            f"{new_state.upper()}",
            flush=True,
        )

    def _enter_active(self) -> None:

        self._set_state(
            self.STATE_ACTIVE
        )

        self.last_interaction = (
            time.monotonic()
        )

    def _return_to_idle(self) -> None:

        self._set_state(
            self.STATE_IDLE
        )

        self.last_interaction = (
            time.monotonic()
        )

    def _enter_guest(self) -> None:

        self._set_state(
            self.STATE_GUEST
        )

        self.last_interaction = (
            time.monotonic()
        )

    def is_idle(self) -> bool:
        return self.state == self.STATE_IDLE

    def is_active(self) -> bool:
        return self.state == self.STATE_ACTIVE

    def is_guest_mode(self) -> bool:
        return self.state == self.STATE_GUEST

    # ==================================================================
    # TEXT NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize(
        text: str,
    ) -> str:

        value = str(
            text or ""
        ).lower()

        replacements = {
            "'": "",
            "’": "",
            ".": " ",
            ",": " ",
            "!": " ",
            "?": " ",
            ":": " ",
            ";": " ",
            "-": " ",
        }

        for old, new in replacements.items():
            value = value.replace(
                old,
                new,
            )

        return " ".join(
            value.split()
        )

    @staticmethod
    def _words(
        text: str,
    ) -> list[str]:

        normalized = (
            VoiceController._normalize(text)
        )

        if not normalized:
            return []

        return normalized.split()

    # ==================================================================
    # POLITE / NATURAL SPEECH CLEANUP
    # ==================================================================

    @staticmethod
    def _strip_politeness(
        text: str,
    ) -> str:

        words = (
            VoiceController._words(text)
        )

        polite_words = {
            "please",
            "thanks",
            "thank",
            "kindly",
            "could",
            "would",
            "can",
        }

        # Remove trailing polite wording only.
        while words and words[-1] in polite_words:
            words.pop()

        # "thank you" / "thanks"
        while len(words) >= 2 and (
            words[-2:] == ["thank", "you"]
            or words[-2:] == ["thanks", "you"]
        ):
            words = words[:-2]

        return " ".join(words)

    # ==================================================================
    # GUEST MODE INTENT DETECTION
    # ==================================================================

    @classmethod
    def _is_guest_enter_command(
        cls,
        command: str,
    ) -> bool:

        normalized = cls._normalize(
            cls._strip_politeness(command)
        )

        if not normalized:
            return False

        exact = {
            "guest mode",
            "enter guest mode",
            "enable guest mode",
            "turn on guest mode",
            "switch to guest mode",
            "go into guest mode",
            "go to guest mode",
            "activate guest mode",
            "start guest mode",
        }

        if normalized in exact:
            return True

        # Natural variants.
        words = normalized.split()

        if "guest" in words and "mode" in words:

            # We deliberately require an action verb so that
            # unrelated conversation mentioning "guest mode"
            # does not switch state accidentally.
            action_words = {
                "enter",
                "enable",
                "turn",
                "switch",
                "go",
                "activate",
                "start",
            }

            if any(
                word in action_words
                for word in words
            ):
                return True

        return False

    @classmethod
    def _is_guest_exit_command(
        cls,
        command: str,
    ) -> bool:

        normalized = cls._normalize(
            cls._strip_politeness(command)
        )

        if not normalized:
            return False

        exact = {
            "aria mode",
            "arias mode",
            "aria s mode",
            "exit guest mode",
            "leave guest mode",
            "end guest mode",
            "disable guest mode",
            "turn off guest mode",
            "switch to aria mode",
            "return to aria mode",
            "go back to aria mode",
        }

        if normalized in exact:
            return True

        words = normalized.split()

        # Guest exit intent.
        if (
            "guest" in words
            and "mode" in words
        ):

            action_words = {
                "exit",
                "leave",
                "end",
                "disable",
                "off",
            }

            if any(
                word in action_words
                for word in words
            ):
                return True

        # ARIA mode is intentionally very explicit.
        if (
            "aria" in words
            and "mode" in words
        ):
            return True

        return False

    # ==================================================================
    # SPECIAL COMMAND HANDLING
    # ==================================================================

    def _handle_special_command(
        self,
        command: str,
    ) -> Optional[str]:

        normalized = self._normalize(
            command
        )

        # --------------------------------------------------------------
        # ENTER GUEST MODE
        # --------------------------------------------------------------

        if self._is_guest_enter_command(
            command
        ):

            already_guest = (
                self.is_guest_mode()
            )

            self._enter_guest()

            if already_guest:

                self._say(
                    "Guest Mode is already on."
                )

            else:

                self._say(
                    "Guest Mode is on."
                )

            print(
                "[VOICE] Guest Mode enabled. "
                "Each interaction now requires ARIA.",
                flush=True,
            )

            return "handled"

        # --------------------------------------------------------------
        # EXIT GUEST MODE / ARIA MODE
        # --------------------------------------------------------------

        if self._is_guest_exit_command(
            command
        ):

            if self.is_guest_mode():

                self._enter_active()

                self._say(
                    "ARIA mode restored."
                )

                print(
                    "[VOICE] Guest Mode disabled. "
                    "Normal ARIA conversation restored.",
                    flush=True,
                )

            else:

                # Already in normal mode.
                self._say(
                    "We're already in ARIA mode."
                )

            return "handled"

        # --------------------------------------------------------------
        # END NORMAL CONVERSATION
        # --------------------------------------------------------------

        if (
            self.is_active()
            and normalized
            in self.CONVERSATION_END_PHRASES
        ):

            self._say(
                "Alright."
            )

            self._return_to_idle()

            return "handled"

        return None

    # ==================================================================
    # COMMAND PROCESSING
    # ==================================================================

    def _process_command(
        self,
        command: str,
    ) -> bool:

        if self._stop_event.is_set():
            return False

        command = str(
            command or ""
        ).strip()

        if not command:
            return True

        print(
            f"[VOICE] You: {command}",
            flush=True,
        )

        self.last_interaction = (
            time.monotonic()
        )

        # IMPORTANT:
        # Controller commands are handled BEFORE
        # the AI sees them.
        special = (
            self._handle_special_command(
                command
            )
        )

        if special == "handled":
            return True

        # Normal user command goes to ARIA's AI.
        try:

            response = (
                self.command_callback(
                    command
                )
            )

        except Exception as exc:

            print(
                f"[VOICE] Command error: {exc}",
                flush=True,
            )

            response = (
                "I ran into a problem "
                "handling that."
            )

        if (
            response
            and not self._stop_event.is_set()
        ):

            print(
                "[VOICE] ARIA is responding.",
                flush=True,
            )

            self._say(
                response
            )

        self.last_interaction = (
            time.monotonic()
        )

        return True

    # ==================================================================
    # SPEECH CAPTURE
    # ==================================================================

    def _capture_command(
        self,
    ) -> Optional[str]:

        if self._stop_event.is_set():
            return None

        try:

            print(
                "[VOICE] READY — your turn. Speak now.",
                flush=True,
            )
            print(
                "[VOICE] Listening...",
                flush=True,
            )

            command = (
                self.speech_listener.listen_once()
            )

            profile = getattr(
                self.speech_listener,
                "last_audio_profile",
                {},
            ) or {}
            logprob = getattr(
                self.speech_listener,
                "last_mean_logprob",
                -10.0,
            )
            compression = getattr(
                self.speech_listener,
                "last_compression_ratio",
                0.0,
            )
            final_confidence = float(
                getattr(
                    self.speech_listener,
                    "last_final_confidence",
                    0.0,
                ) or 0.0
            )
            print(
                "[ARIA DECISION] "
                f"transcript_confidence={final_confidence:.3f} "
                f"singing={float(profile.get('singing_score', 0.0) or 0.0):.2f} "
                f"speech={float(profile.get('speech_likeness', 0.0) or 0.0):.2f}",
                flush=True,
            )

            print(
                "[VOICE] CAPTURE RESULT: "
                f"duration={float(profile.get('duration', 0.0) or 0.0):.2f}s "
                f"logprob={float(logprob):.2f} "
                f"compression={float(compression):.2f} "
                f"singing={float(profile.get('singing_score', 0.0) or 0.0):.2f} "
                f"speech={float(profile.get('speech_likeness', 0.0) or 0.0):.2f} "
                f"final_conf={final_confidence:.3f}",
                flush=True,
            )

            if self._stop_event.is_set():
                return None

            if not command:

                print(
                    "[VOICE] "
                    "No reliable speech detected.",
                    flush=True,
                )

                return None

            command = str(
                command
            ).strip()

            if not command:

                print(
                    "[VOICE] "
                    "No reliable speech detected.",
                    flush=True,
                )

                return None

            return command

        except Exception as exc:

            if not self._stop_event.is_set():

                print(
                    f"[VOICE] "
                    f"Speech capture error: {exc}",
                    flush=True,
                )

            return None

    # ==================================================================
    # ACTIVE-MODE ATTENTION GATE
    # ==================================================================

    # These are intentionally conservative.  They are used ONLY after ARIA
    # has already been explicitly activated, so normal commands remain easy
    # to issue while background conversation, singing, and call backchannel
    # are much less likely to reach the AI.
    ATTENTION_QUESTION_STARTERS = {
        "what",
        "whats",
        "why",
        "when",
        "where",
        "who",
        "whose",
        "which",
        "how",
        "can",
        "could",
        "would",
        "will",
        "should",
        "do",
        "does",
        "did",
        "is",
        "are",
        "am",
        "have",
        "has",
        "tell",
        "explain",
    }

    ATTENTION_ACTION_WORDS = {
        "open",
        "close",
        "launch",
        "start",
        "stop",
        "run",
        "mute",
        "unmute",
        "restore",
        "calculate",
        "check",
        "show",
        "find",
        "search",
        "play",
        "pause",
        "resume",
        "turn",
        "enable",
        "disable",
        "enter",
        "exit",
        "switch",
        "set",
        "get",
        "make",
        "create",
        "remember",
        "forget",
        "help",
    }

    ATTENTION_RECOVERY_PATTERNS = (
        r"\bi need (you|help)\b",
        r"\bi want (you|to)\b",
        r"\bi d like (you|to)\b",
        r"\bi would like (you|to)\b",
        r"\bi have a question\b",
        r"\bhelp me\b",
        r"\bcould you\b",
        r"\bcan you\b",
        r"\bwould you\b",
        r"\bwill you\b",
        r"\bplease\b",
        r"\btell me\b",
        r"\bshow me\b",
    )

    ATTENTION_DIRECT_PATTERNS = (
        r"\baria\b",
        r"\bcan you\b",
        r"\bcould you\b",
        r"\bwould you\b",
        r"\bwill you\b",
        r"\bdo you\b",
        r"\bdid you\b",
        r"\bare you\b",
        r"\bplease\b",
        r"\btell me\b",
        r"\bshow me\b",
        r"\bwhat do you think\b",
        r"\bwhat do you remember\b",
    )

    ATTENTION_CALL_BACKCHANNELS = {
        "yeah",
        "yea",
        "yep",
        "yup",
        "nope",
        "nah",
        "okay",
        "ok",
        "alright",
        "right",
        "sure",
        "exactly",
        "fair enough",
        "sounds good",
        "thats fine",
        "that's fine",
        "no worries",
        "one sec",
        "one second",
        "hold on",
        "hang on",
        "sorry",
        "hello",
        "hi",
        "hey",
        "thanks",
        "thank you",
        "cheers",
    }

    ATTENTION_SELF_TALK_PATTERNS = (
        r"^i am ",
        r"^im ",
        r"^i'm ",
        r"^i was ",
        r"^i were ",
        r"^i know ",
        r"^i think ",
        r"^i feel ",
        r"^i need to ",
        r"^i should ",
        r"^i want to ",
        r"^i wish ",
        r"^i wonder ",
        r"^i guess ",
        r"^i suppose ",
        r"^i can ",
        r"^i could ",
    )

    @staticmethod
    def _looks_repetitive_speech(words: list[str]) -> bool:
        if len(words) < 6:
            return False

        unique_words = len(set(words))
        repetition_ratio = 1.0 - (unique_words / max(1, len(words)))

        # Immediate repeated-word chains are especially common in lyrics
        # and singing transcripts.
        adjacent_repeats = 0
        for left, right in zip(words, words[1:]):
            if left == right:
                adjacent_repeats += 1

        return repetition_ratio >= 0.15 or adjacent_repeats >= 2

    @classmethod
    def _active_attention_decision(
        cls,
        command: str,
        recovery_mode: bool = False,
    ) -> tuple[bool, str]:
        """
        Decide whether continuous-mode speech is probably directed at ARIA.

        This is deliberately deterministic and conservative.  It is NOT used
        for the first command after wake, nor in Guest Mode.  Explicit ARIA
        addressing always wins, which gives the user a reliable escape hatch
        while on a call or speaking to someone else.
        """
        raw = str(command or "").strip()
        normalized = cls._normalize(raw)
        words = normalized.split()

        if not normalized:
            return False, "empty"

        # Explicitly addressing ARIA always wins.
        if re.search(r"\baria\b", normalized):
            return True, "explicit_aria"

        # Special commands and clearly assistant-directed phrases should pass.
        if cls._is_guest_enter_command(raw) or cls._is_guest_exit_command(raw):
            return True, "controller_command"

        for pattern in cls.ATTENTION_DIRECT_PATTERNS:
            if re.search(pattern, normalized):
                return True, "direct_request"

        # Questions survive even when Whisper omitted punctuation.
        if words and words[0] in cls.ATTENTION_QUESTION_STARTERS:
            return True, "question"

        # Clear action commands remain conversationally natural.
        if words and words[0] in cls.ATTENTION_ACTION_WORDS:
            return True, "command"

        # Common call/backchannel phrases are almost never intended for ARIA.
        if normalized in cls.ATTENTION_CALL_BACKCHANNELS:
            return False, "call_backchannel"

        # Recovery mode is entered after singing/background speech has just
        # been rejected.  This gives the user a reliable way to immediately
        # resume talking without needing to say ARIA again.
        if recovery_mode:
            for pattern in cls.ATTENTION_RECOVERY_PATTERNS:
                if re.search(pattern, normalized):
                    return True, "recovery_direct_request"

            # A medium/long utterance containing a clear second-person
            # reference is also likely to be directed at ARIA.  Repetition
            # checks below still protect obvious lyrics.
            if (
                len(words) >= 5
                and any(word in {"you", "your", "yours", "me", "my"} for word in words)
                and not cls._looks_repetitive_speech(words)
            ):
                return True, "recovery_second_person"

            # A natural sentence after singing/background speech is treated as
            # a fresh attention attempt.  This is the important recovery path:
            # it lets the user resume ordinary conversation without saying ARIA
            # again, while the repetition check continues to block lyric-like
            # material.
            if (
                len(words) >= 5
                and not cls._looks_repetitive_speech(words)
            ):
                return True, "recovery_natural_speech"

        # First-person declaratives are a strong signal of self-talk rather
        # than assistant-directed speech.  Explicit questions/requests above
        # have already been allowed.
        for pattern in cls.ATTENTION_SELF_TALK_PATTERNS:
            if re.search(pattern, normalized):
                return False, "self_talk"

        # Longer conversational passages without an explicit request are much
        # more likely to be singing, talking to another person, or being on a
        # call than talking to ARIA.
        if len(words) >= 8:
            if cls._looks_repetitive_speech(words):
                return False, "repetitive_or_song_like"
            return False, "long_background_speech"

        # Short statements that are not questions, commands, or explicit
        # requests are still ambiguous; ignore them rather than interrupting
        # the user's private conversation.
        if len(words) <= 4:
            return False, "ambiguous_short_speech"

        return False, "background_speech"

    # ==================================================================
    # NORMAL ARIA MODE
    # ==================================================================

    def _run_active_mode(self) -> None:
        """
        Continuous normal ARIA conversation.

        There is intentionally no inactivity timeout.
        """

        missed_captures = 0
        capture_failures = 0

        while (
            self.running
            and self.state
            == self.STATE_ACTIVE
            and not self._stop_event.is_set()
        ):

            command = (
                self._capture_command()
            )

            if command:
                capture_failures = 0

                # Once ARIA is active, do not treat every sound picked up by
                # the microphone as an instruction.  This protects against
                # singing, self-talk, and ordinary call/background speech
                # without changing the initial wake -> first-command path.
                normalized_command = self._normalize(command)
                if normalized_command in {
                    "what is the time",
                    "what is time",
                    "what's the time",
                    "whats the time",
                    "tell me the time",
                }:
                    command = "what's the time"
                    print(
                        "[INTENT] Deterministic time intent selected.",
                        flush=True,
                    )

                accepted, reason = self._active_attention_decision(
                    command,
                    recovery_mode=self._attention_recovery,
                )

                if not accepted:
                    print(
                        "[VOICE] Attention gate ignored: "
                        f"{reason} | {command}",
                        flush=True,
                    )
                    self._attention_recovery = reason in {
                        "repetitive_or_song_like",
                        "long_background_speech",
                        "background_speech",
                        "self_talk",
                        "ambiguous_short_speech",
                    }
                    continue

                missed_captures = 0
                self._attention_recovery = False

                if not self._process_command(
                    command
                ):
                    return

                continue

            missed_captures += 1
            capture_failures += 1

            if capture_failures in {1, 3, 6}:
                print(
                    f"[VOICE] Capture returned no reliable command "
                    f"(attempt={capture_failures}); keeping ARIA active.",
                    flush=True,
                )

            if (
                missed_captures >= 3
            ):

                print(
                    "[VOICE] "
                    "No reliable speech detected; "
                    "continuing normal ARIA mode.",
                    flush=True,
                )

                missed_captures = 0

            time.sleep(0.15)

    # ==================================================================
    # GUEST MODE
    # ==================================================================

    def _run_guest_interaction(
        self,
    ) -> None:

        if (
            not self.running
            or self.state
            != self.STATE_GUEST
        ):
            return

        print(
            "[VOICE] Guest Mode waiting "
            "for ARIA wake word...",
            flush=True,
        )

        detected = False

        try:

            detected = (
                self._wake_listener.listen_once()
            )

        except Exception as exc:

            if self.running:

                print(
                    f"[WAKE] Guest wake error: {exc}",
                    flush=True,
                )

            return

        if not detected:
            return

        self._pause_wake_listener()

        try:

            if (
                not self.running
                or self.state
                != self.STATE_GUEST
            ):
                return

            self._say_wake_response()

            command = (
                self._capture_command()
            )

            if not command:

                print(
                    "[VOICE] Guest command "
                    "was not reliable; "
                    "returning to guest wake.",
                    flush=True,
                )

                return

            self._process_command(
                command
            )

        finally:

            if (
                self.running
                and self.state
                == self.STATE_GUEST
            ):

                self._resume_wake_listener()

                print(
                    "[VOICE] Guest Mode remains active; "
                    "waiting for ARIA wake word.",
                    flush=True,
                )

    # ==================================================================
    # INITIAL WAKE
    # ==================================================================

    def _handle_initial_wake(
        self,
    ) -> None:

        if not self.running:
            return

        self._pause_wake_listener()

        try:

            self._enter_active()

            print(
                "[VOICE] Wake accepted. "
                "Speaking acknowledgement...",
                flush=True,
            )

            self._say_wake_response()

            if not self.running:
                return

            print(
                "[VOICE] Wake response complete.",
                flush=True,
            )

            print(
                "[VOICE] Now listening for your command...",
                flush=True,
            )

            command = (
                self._capture_command()
            )

            if not command:

                print(
                    "[VOICE] Initial command "
                    "was not reliable; "
                    "staying in normal ARIA mode.",
                    flush=True,
                )

                return

            self._process_command(
                command
            )

            # If Guest Mode was entered, do NOT
            # return to normal ACTIVE behaviour.
            if (
                self.running
                and self.state
                == self.STATE_ACTIVE
            ):

                print(
                    "[VOICE] Normal ARIA mode active; "
                    "wake word is no longer required.",
                    flush=True,
                )

            elif (
                self.running
                and self.state
                == self.STATE_GUEST
            ):

                print(
                    "[VOICE] Guest Mode active; "
                    "next interaction requires ARIA.",
                    flush=True,
                )

        except Exception as exc:

            if self.running:

                print(
                    f"[VOICE] "
                    f"Wake handling failed: {exc}",
                    flush=True,
                )

            self._return_to_idle()

        finally:

            self._stop_barge_listener()

            # Only resume the wake listener if we are
            # actually waiting for it.
            if (
                self.running
                and (
                    self.state
                    == self.STATE_IDLE
                    or self.state
                    == self.STATE_GUEST
                )
            ):

                self._resume_wake_listener()

    # ==================================================================
    # WAKE LISTENER CONTROL
    # ==================================================================

    def _pause_wake_listener(
        self,
    ) -> None:

        try:
            self._wake_listener.pause()
        except Exception:
            pass

    def _resume_wake_listener(
        self,
    ) -> None:

        try:
            self._wake_listener.resume()
        except Exception as exc:

            print(
                f"[WAKE] Resume failed: {exc}",
                flush=True,
            )

    # ==================================================================
    # MAIN LOOP
    # ==================================================================

    def _run(self) -> None:

        print(
            "[VOICE] Voice loop running.",
            flush=True,
        )

        while (
            self.running
            and not self._stop_event.is_set()
        ):

            try:

                # ------------------------------------------------------
                # IDLE
                # ------------------------------------------------------

                if self.state == self.STATE_IDLE:

                    detected = (
                        self._wake_listener.listen_once()
                    )

                    if detected:

                        self._handle_initial_wake()

                    else:

                        time.sleep(0.05)

                    continue

                # ------------------------------------------------------
                # NORMAL ARIA
                # ------------------------------------------------------

                if self.state == self.STATE_ACTIVE:

                    self._run_active_mode()

                    continue

                # ------------------------------------------------------
                # GUEST MODE
                # ------------------------------------------------------

                if self.state == self.STATE_GUEST:

                    self._run_guest_interaction()

                    time.sleep(0.05)

                    continue

                # ------------------------------------------------------
                # SAFETY FALLBACK
                # ------------------------------------------------------

                self._return_to_idle()

            except Exception as exc:

                if self.running:

                    print(
                        f"[VOICE] "
                        f"Controller error: {exc}",
                        flush=True,
                    )

                time.sleep(0.5)

    # ==================================================================
    # START
    # ==================================================================

    def start(self) -> None:

        if self.running:
            return

        self._stop_event.clear()

        self.running = True

        self._set_state(
            self.STATE_IDLE
        )

        self._thread = threading.Thread(
            target=self._run,
            name="ARIA-VoiceController",
            daemon=True,
        )

        self._thread.start()

        print(
            "[VOICE] Controller thread started; ARIA lifetime protected.",
            flush=True,
        )

    # ==================================================================
    # STOP
    # ==================================================================

    def stop(self) -> None:

        if not self.running:
            return

        print(
            "[VOICE] Shutting down...",
            flush=True,
        )

        self.running = False

        self._stop_event.set()

        self._stop_barge_listener()

        try:
            self.speaker.stop()
        except Exception:
            pass

        try:
            self._wake_listener.close()
        except Exception:
            pass

        if self._barge_listener is not None:

            try:
                self._barge_listener.close()
            except Exception:
                pass

        self._set_state(
            self.STATE_IDLE
        )

        if (
            self._thread is not None
            and self._thread.is_alive()
            and self._thread
            is not threading.current_thread()
        ):

            self._thread.join(
                timeout=2.0
            )

        self._thread = None

        print(
            "[VOICE] Offline.",
            flush=True,
        )