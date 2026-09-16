from __future__ import annotations

import json
import re
from typing import Any, Callable

from ollama import chat
from memory.character_memory import CharacterMemory


class AIBrain:
    """
    Local reasoning layer for A.R.I.A.

    The model is explicitly instructed to:
    - understand the user's intent rather than mimic the transcript;
    - prefer real tools over explaining how the user could do something;
    - never invent certainty;
    - ask for clarification when speech is genuinely ambiguous;
    - distinguish a failed action from a successful action;
    - avoid making guesses based on a single suspicious word.

    Character learning is integrated here only for persistent people memory.
    No voice, media, wake-word, or application-control code is changed here.
    """

    def __init__(self, model: str = "qwen2.5:7b") -> None:
        self.model = model
        self.character_memory = CharacterMemory()
        self._guest_mode = False

        self.system_prompt = r"""
You are A.R.I.A. — Adaptive Reasoning & Intelligent Assistant.

You are Beau's personal local desktop assistant.

CORE BEHAVIOUR

1. UNDERSTAND INTENT, NOT JUST WORDS
- Infer the user's intended task from the complete sentence and the current
  conversation context.
- Do not mechanically respond to isolated words.
- Use recent conversation context when the user says things like "it",
  "that one", "same thing", "unmute it", "open that", or similar references.
- When the user's wording is imperfect but the intended meaning is clear from
  context, understand it naturally.
- When two materially different interpretations remain possible, ask one
  concise clarification question instead of guessing.

2. SPEECH TRANSCRIPTS MAY BE IMPERFECT
The microphone system can occasionally produce a slightly incorrect
transcript. Treat strange wording as potentially imperfect speech recognition.
Do NOT confidently invent a meaning from nonsense.

Examples:
- "on mute brave" can reasonably mean "unmute Brave" when the conversation is
  already about Brave audio.
- "unmute phrase" is NOT enough evidence to create or control an application
  called Phrase.
- If a transcript appears corrupted and there is no strong contextual answer,
  ask the user to repeat it.

3. USE TOOLS FOR ACTIONS
When the user asks ARIA to perform an action that a real tool can perform,
USE THE TOOL.
Do not give the user instructions for doing it manually instead.
Do not say "right-click Brave" when a mute/unmute tool is available.

Direct-action examples:
- "mute Brave" -> mute_application
- "unmute Brave" -> unmute_application
- "open Roblox" -> launch/open tool
- "close Roblox" -> close tool
- "check my system" -> get_system_status

4. TOOL RESULTS ARE AUTHORITATIVE
- STATUS=SUCCESS means the action succeeded.
- STATUS=STARTED means the requested action was started/accepted, not that
  final state has been independently verified.
- STATUS=FAILED means it failed.
- STATUS=NOT_FOUND means the requested resource was not found.
- Never convert failure into success language.
- Never claim you personally observed a result that the tool did not report.

5. NEVER CONTROL THE MICROPHONE
ARIA does NOT mute, unmute, disable, or enable the physical microphone.
If asked to do so, say that microphone hardware control is not available.
Do not call a microphone-control tool.

6. SYSTEM MONITORING
- CPU means CPU utilization, processor count, and frequency.
- GPU may include temperature if the GPU tool provides it.
- Do not invent CPU temperature.
- Do not mention external hardware-monitoring software as a required dependency.

7. CONVERSATION
- Be natural and context-aware.
- Avoid excessive filler.
- Do not restate the user's request unless useful.
- If the user asks a simple question, answer directly.
- If the user asks you to do something, do it rather than explaining how they
  could do it themselves.
- Maintain continuity across follow-up turns.

8. CHARACTER MEMORY
ARIA has persistent local memory for people Beau talks about.

Only remember information that is:
- explicitly stated by Beau;
- useful beyond the immediate sentence;
- reasonably durable;
- relevant to understanding that person later.

Good examples:
- "Gracie is my girlfriend."
- "James works with me."
- "Sarah loves drawing."
- "Tom hates coffee."
- "Emily has started learning Blender."
- "I call Samantha Sam."
- "Josh is helping me with the ARIA project."

Do NOT treat every mention of a person as something worth remembering.

Do NOT create or update a person profile merely because:
- the person's name was mentioned;
- Beau asked a question about that person;
- Beau asked what ARIA remembers about them;
- Beau asked who they are;
- Beau said hello to them;
- Beau mentioned seeing them once;
- Beau referred to them in a temporary situation with no durable information.

Do not invent facts, biography, motives, relationships, or sensitive attributes.
Do not treat a guess as a fact.
Do not silently erase previous observations when a new statement changes them.
Treat new information as a newer observation.

9. SAFETY AND CONTROL
- Never perform destructive actions without the required confirmation.
- Do not delete things without asking.
- Do not invent permissions or capabilities.

10. PRIVACY
You are in Beau's normal ARIA mode unless the application explicitly tells you
that Guest Mode is active.
Do not reveal private owner context to guests.

11. UNCERTAINTY
A wrong confident action is worse than a brief clarification.
When evidence is weak, say so.
"Memory" means previously observed information, not guaranteed truth.
"Confidence" should never be treated as certainty.
"""

        self.guest_system_prompt = r"""
You are A.R.I.A. in GUEST MODE.

Guest Mode is public-facing and privacy-restricted.

- Do not reveal Beau's private memories, private conversation context,
  personal history, secrets, account information, or owner-only details.
- Treat the guest as a separate conversational user.
- You may still use safe system/application tools when the request is
  authorized by the application's available tool set.
- Use tools for real actions instead of explaining manual steps.
- Never claim an action succeeded unless the tool confirms it.
- If speech or intent is ambiguous, ask for clarification rather than guessing.
- You do not control or mute the physical microphone.
- CPU monitoring means utilization, not CPU temperature.
- Character-memory learning is disabled in Guest Mode.
- Be friendly, clear, and concise.
"""

    def set_guest_mode(self, enabled: bool) -> None:
        self._guest_mode = bool(enabled)

    def is_guest_mode(self) -> bool:
        return self._guest_mode

    # ------------------------------------------------------------------
    # CHARACTER MEMORY — INTERNAL LEARNING
    # ------------------------------------------------------------------

    @staticmethod
    def _is_memory_query(text: str) -> bool:
        """
        Return True when the user is asking about existing memory rather than
        providing new information to remember.
        """
        normalized = re.sub(
            r"\s+",
            " ",
            str(text or "").strip().lower(),
        )

        if not normalized:
            return True

        query_patterns = (
            r"\bwhat do you remember\b",
            r"\bwhat do you know\b",
            r"\btell me about\b",
            r"\bwhat can you tell me about\b",
            r"\bdo you remember\b",
            r"\bdo you know\b",
            r"\bwho is\b",
            r"\bwho's\b",
            r"\bwho was\b",
            r"\bwhat is\b",
            r"\bwhat's\b",
            r"\bwhat was\b",
            r"\banything about\b",
            r"\banything you remember\b",
            r"\bwhat have you learned\b",
            r"\bwhat have you saved\b",
            r"\bwhat have you stored\b",
        )

        return any(
            re.search(
                pattern,
                normalized,
            )
            for pattern in query_patterns
        )

    @staticmethod
    def _has_learning_signal(text: str) -> bool:
        """
        Cheap first-pass filter.

        Character extraction is only needed when the message contains language
        that plausibly introduces durable information.
        """
        normalized = re.sub(
            r"\s+",
            " ",
            str(text or "").strip().lower(),
        )

        if not normalized:
            return False

        learning_patterns = (
            r"\bmy (girlfriend|boyfriend|partner|wife|husband|friend|brother|sister|mum|mom|dad|father|mother|son|daughter|boss|manager|coworker|co-worker|colleague)\b",
            r"\bis my\b",
            r"\bare my\b",
            r"\bworks? (at|for|with)\b",
            r"\bworked? (at|for|with)\b",
            r"\blives? (in|at|near)\b",
            r"\bfrom\b",
            r"\bcalled\b",
            r"\bknown as\b",
            r"\bnamed\b",
            r"\bname is\b",
            r"\bi call\b",
            r"\bwe call\b",
            r"\b(loves?|likes?|hates?|dislikes?|prefers?)\b",
            r"\b(enjoys?|avoids?|uses?|plays?|works on|studies?|learns?|learning)\b",
            r"\b(started|began|joined|left|moved|works|worked)\b",
            r"\b(helps?|helped?) me\b",
            r"\bhelping me\b",
            r"\bknows? me\b",
            r"\bmet\b",
        )

        return any(
            re.search(
                pattern,
                normalized,
            )
            for pattern in learning_patterns
        )

    @staticmethod
    def _has_useful_person_data(person: dict[str, Any]) -> bool:
        """
        Prevent saving a profile when the model returned only a person's name.
        """
        relationship = str(
            person.get(
                "relationship",
                "",
            )
            or ""
        ).strip()

        if relationship:
            return True

        fields = (
            "aliases",
            "traits",
            "preferences",
            "dislikes",
            "interests",
            "facts",
            "notes",
        )

        for field in fields:
            value = person.get(
                field,
                [],
            )

            if isinstance(
                value,
                str,
            ):
                if value.strip():
                    return True

            elif isinstance(
                value,
                list,
            ):
                for item in value:
                    if str(item).strip():
                        return True

        return False

    def _learn_characters(
        self,
        latest_user: str,
        guest_mode: bool,
    ) -> None:
        """
        Extract only durable, explicitly supported people information.

        This runs before the normal reasoning request and writes only to the
        CharacterMemory store. It does not touch ToolRouter or any other ARIA
        subsystem.
        """
        if guest_mode:
            return

        latest_user = str(
            latest_user or ""
        ).strip()

        if not latest_user:
            return

        # Questions about existing memory must never become new memory.
        if self._is_memory_query(
            latest_user
        ):
            return

        # Ignore ordinary conversation unless there is a plausible signal that
        # durable information is actually being provided.
        if not self._has_learning_signal(
            latest_user
        ):
            return

        extraction_prompt = r"""
Extract only genuinely useful, durable character information from Beau's
message.

Return ONLY valid JSON in this exact shape:

{
  "people": [
    {
      "name": "string",
      "relationship": "string",
      "aliases": [],
      "traits": [],
      "preferences": [],
      "dislikes": [],
      "interests": [],
      "facts": [],
      "notes": []
    }
  ]
}

Rules:

- Only include real people explicitly identifiable from the message.
- The person must have at least one genuinely useful piece of information.
- A person's name appearing in the sentence is NOT enough.
- Do not create a profile from a temporary mention.
- Do not create a profile from a question about the person.
- Only record information explicitly stated or strongly established by the
  message. Never invent missing information.
- "Gracie is my girlfriend" means relationship="girlfriend".
- "Gracie loves drawing" means preferences or interests may contain "drawing".
- "Gracie hates coffee" means dislikes may contain "coffee".
- "James works with me" is an important fact.
- "I call Samantha Sam" is an alias.
- "Josh is helping me with the ARIA project" is a useful relationship/context
  fact.
- "I saw Gracie yesterday" by itself is NOT durable enough to remember.
- "Gracie was at my house yesterday" by itself is NOT durable enough to remember.
- Do not infer age, sexuality, religion, politics, medical information,
  ethnicity, or other sensitive attributes.
- Do not turn opinions into objective facts.
- Keep each item short and faithful to the user's wording.
- Return an empty people list when there is nothing durable to remember.
"""

        try:
            extraction = chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": extraction_prompt,
                    },
                    {
                        "role": "user",
                        "content": latest_user,
                    },
                ],
                format="json",
                options={
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "repeat_penalty": 1.0,
                },
                keep_alive=-1,
            )

            raw = str(
                extraction.message.content
                or ""
            ).strip()

            if not raw:
                return

            data = json.loads(
                raw
            )

            if not isinstance(
                data,
                dict,
            ):
                return

            people = data.get(
                "people",
                [],
            )

            if not isinstance(
                people,
                list,
            ):
                return

            for person in people:
                if not isinstance(
                    person,
                    dict,
                ):
                    continue

                name = str(
                    person.get(
                        "name",
                        "",
                    )
                ).strip()

                if not name:
                    continue

                # Never save a profile containing only a person's name.
                if not self._has_useful_person_data(
                    person
                ):
                    continue

                self.character_memory.remember_person(
                    name=name,
                    relationship=str(
                        person.get(
                            "relationship",
                            "",
                        )
                        or ""
                    ),
                    facts=" | ".join(
                        self._safe_memory_list(
                            person.get(
                                "facts",
                                [],
                            )
                        )
                    ),
                    preferences=" | ".join(
                        self._safe_memory_list(
                            person.get(
                                "preferences",
                                [],
                            )
                        )
                    ),
                    dislikes=" | ".join(
                        self._safe_memory_list(
                            person.get(
                                "dislikes",
                                [],
                            )
                        )
                    ),
                    traits=" | ".join(
                        self._safe_memory_list(
                            person.get(
                                "traits",
                                [],
                            )
                        )
                    ),
                    interests=" | ".join(
                        self._safe_memory_list(
                            person.get(
                                "interests",
                                [],
                            )
                        )
                    ),
                    aliases=" | ".join(
                        self._safe_memory_list(
                            person.get(
                                "aliases",
                                [],
                            )
                        )
                    ),
                    notes=" | ".join(
                        self._safe_memory_list(
                            person.get(
                                "notes",
                                [],
                            )
                        )
                    ),
                    source=latest_user,
                )

                print(
                    f"[CHARACTER MEMORY] Learned from: {name}",
                    flush=True,
                )

        except Exception as exc:
            # Character learning must never break the normal assistant.
            print(
                f"[CHARACTER MEMORY] Learning skipped: {exc}",
                flush=True,
            )

    @staticmethod
    def _safe_memory_list(
        value: Any,
    ) -> list[str]:

        if isinstance(
            value,
            str,
        ):
            return [
                value.strip()
            ] if value.strip() else []

        if not isinstance(
            value,
            list,
        ):
            return []

        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    def _character_context(
        self,
        latest_user: str,
        guest_mode: bool,
    ) -> str:

        if guest_mode:
            return ""

        try:
            return self.character_memory.context_for_text(
                latest_user
            )

        except Exception as exc:
            print(
                f"[CHARACTER MEMORY] Context skipped: {exc}",
                flush=True,
            )
            return ""

    # ------------------------------------------------------------------
    # REASONING
    # ------------------------------------------------------------------

    def ask(
        self,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
        guest_mode: bool | None = None,
    ) -> Any:

        if guest_mode is None:
            guest_mode = self._guest_mode
        else:
            guest_mode = bool(guest_mode)
            self._guest_mode = guest_mode

        latest_user = ""

        for message in reversed(
            messages
        ):
            if message.get(
                "role"
            ) == "user":
                latest_user = str(
                    message.get(
                        "content",
                        "",
                    )
                )
                break

        # Learn from the latest owner message before answering so that the
        # relevant profile can be available immediately in the response.
        self._learn_characters(
            latest_user,
            guest_mode,
        )

        prompt = (
            self.guest_system_prompt
            if guest_mode
            else self.system_prompt
        )

        character_context = self._character_context(
            latest_user,
            guest_mode,
        )

        if character_context:
            prompt += (
                "\n\n"
                "RELEVANT PERSISTENT CHARACTER MEMORY\n"
                "These are remembered observations from previous conversations.\n"
                "Use them naturally when relevant. They are observations, not absolute truth.\n"
                + character_context
            )

        full_messages = [
            {
                "role": "system",
                "content": prompt,
            },
            *messages,
        ]

        return chat(
            model=self.model,
            messages=full_messages,
            tools=tools or [],
            options={
                "temperature": 0.12,
                "top_p": 0.9,
                "repeat_penalty": 1.05,
            },
            keep_alive=-1,
        )