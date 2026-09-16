from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


class CharacterMemory:
    """
    Persistent memory for people ARIA learns about.

    Profiles are stored locally in:
        A:/Core/Project/memory/characters.json

    Design goals:
    - Learn incrementally.
    - Preserve previous observations.
    - Do not silently erase contradictory information.
    - Keep evidence for why something is believed.
    - Never invent facts inside this class.
    - Keep profiles local to Beau's ARIA installation.
    """

    def __init__(
        self,
        project_root: Path | None = None,
    ) -> None:

        if project_root is None:
            project_root = (
                Path(__file__).resolve().parent.parent
            )

        self.project_root = Path(project_root)

        self.memory_dir = (
            self.project_root / "memory"
        )

        self.memory_path = (
            self.memory_dir / "characters.json"
        )

        self.memory_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.data = self._load()

    # ================================================================
    # BASIC STORAGE
    # ================================================================

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(
            timespec="seconds"
        )

    @staticmethod
    def _normalize(value: str) -> str:
        value = str(
            value or ""
        ).strip().lower()

        value = re.sub(
            r"[^\w\s'-]",
            " ",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()

    @staticmethod
    def _clean_list(
        values: Any,
    ) -> list[str]:

        if values is None:
            return []

        if isinstance(values, str):

            values = [
                item.strip()
                for item in values.split("|")
            ]

        if not isinstance(
            values,
            (list, tuple, set),
        ):
            return []

        result: list[str] = []

        for value in values:

            value = str(
                value or ""
            ).strip()

            if not value:
                continue

            if value not in result:
                result.append(value)

        return result

    def _load(self) -> dict[str, Any]:

        if not self.memory_path.exists():

            data = {
                "version": 1,
                "updated_at": self._now(),
                "profiles": {},
            }

            self._save_data(data)

            return data

        try:

            with self.memory_path.open(
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(file)

        except (
            OSError,
            json.JSONDecodeError,
        ):

            print(
                "[CHARACTER MEMORY] "
                "Memory file was unavailable; "
                "starting with an empty profile set.",
                flush=True,
            )

            return {
                "version": 1,
                "updated_at": self._now(),
                "profiles": {},
            }

        if not isinstance(
            data,
            dict,
        ):

            return {
                "version": 1,
                "updated_at": self._now(),
                "profiles": {},
            }

        if not isinstance(
            data.get("profiles"),
            dict,
        ):

            data["profiles"] = {}

        return data

    def _save_data(
        self,
        data: dict[str, Any],
    ) -> None:

        temp_path = (
            self.memory_path.with_suffix(
                ".tmp"
            )
        )

        with temp_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False,
            )

        temp_path.replace(
            self.memory_path
        )

    def _save(self) -> None:

        self.data["updated_at"] = (
            self._now()
        )

        self._save_data(
            self.data
        )

    # ================================================================
    # PROFILE HELPERS
    # ================================================================

    def _profile_key(
        self,
        name: str,
    ) -> str:

        normalized = self._normalize(
            name
        )

        return normalized.replace(
            " ",
            "_",
        )

    def _new_profile(
        self,
        name: str,
    ) -> dict[str, Any]:

        now = self._now()

        return {
            "name": name.strip(),
            "aliases": [],
            "relationship": "",
            "traits": [],
            "preferences": [],
            "dislikes": [],
            "interests": [],
            "important_facts": [],
            "observations": [],
            "contradictions": [],
            "interaction_count": 0,
            "confidence": 0.25,
            "first_seen": now,
            "last_seen": now,
            "created_at": now,
            "updated_at": now,
        }

    # ================================================================
    # PERSON LOOKUP
    # ================================================================

    def find_profile(
        self,
        name: str,
    ) -> dict[str, Any] | None:

        normalized = self._normalize(
            name
        )

        if not normalized:
            return None

        profiles = self.data.get(
            "profiles",
            {},
        )

        direct_key = self._profile_key(
            name
        )

        if direct_key in profiles:

            return profiles[
                direct_key
            ]

        for profile in profiles.values():

            profile_name = self._normalize(
                profile.get(
                    "name",
                    "",
                )
            )

            if profile_name == normalized:
                return profile

            for alias in profile.get(
                "aliases",
                [],
            ):

                if self._normalize(
                    alias
                ) == normalized:

                    return profile

        return None

    def _find_or_create_profile(
        self,
        name: str,
    ) -> tuple[str, dict[str, Any]]:

        existing = self.find_profile(
            name
        )

        if existing is not None:

            key = self._profile_key(
                existing["name"]
            )

            return key, existing

        clean_name = str(
            name or ""
        ).strip()

        if not clean_name:
            raise ValueError(
                "A character name is required."
            )

        key = self._profile_key(
            clean_name
        )

        profile = self._new_profile(
            clean_name
        )

        self.data.setdefault(
            "profiles",
            {},
        )[key] = profile

        return key, profile

    # ================================================================
    # LEARNING
    # ================================================================

    def remember_person(
        self,
        name: str,
        relationship: str = "",
        facts: str = "",
        preferences: str = "",
        dislikes: str = "",
        traits: str = "",
        interests: str = "",
        aliases: str = "",
        notes: str = "",
        source: str = "",
    ) -> str:

        """
        Add new information to a person's persistent profile.

        The AI supplies only information it believes was explicitly
        stated or strongly established by the user.
        """

        key, profile = (
            self._find_or_create_profile(
                name
            )
        )

        now = self._now()

        profile[
            "interaction_count"
        ] = int(
            profile.get(
                "interaction_count",
                0,
            )
        ) + 1

        profile[
            "last_seen"
        ] = now

        profile[
            "updated_at"
        ] = now

        relationship = str(
            relationship or ""
        ).strip()

        if relationship:

            old_relationship = str(
                profile.get(
                    "relationship",
                    "",
                )
            ).strip()

            if (
                old_relationship
                and old_relationship.lower()
                != relationship.lower()
            ):

                contradiction = (
                    f"Previous relationship: "
                    f"{old_relationship}; "
                    f"new observation: "
                    f"{relationship}."
                )

                if contradiction not in profile[
                    "contradictions"
                ]:

                    profile[
                        "contradictions"
                    ].append(
                        contradiction
                    )

            else:

                profile[
                    "relationship"
                ] = relationship

        aliases_list = self._clean_list(
            aliases
        )

        for alias in aliases_list:

            if (
                alias.lower()
                != profile[
                    "name"
                ].lower()
                and alias not in profile[
                    "aliases"
                ]
            ):

                profile[
                    "aliases"
                ].append(alias)

        fields = {
            "important_facts": self._clean_list(
                facts
            ),
            "preferences": self._clean_list(
                preferences
            ),
            "dislikes": self._clean_list(
                dislikes
            ),
            "traits": self._clean_list(
                traits
            ),
            "interests": self._clean_list(
                interests
            ),
        }

        added_items: list[str] = []

        for field_name, items in fields.items():

            existing_items = profile.setdefault(
                field_name,
                [],
            )

            for item in items:

                if item not in existing_items:

                    existing_items.append(
                        item
                    )

                    added_items.append(
                        f"{field_name}: {item}"
                    )

        source_text = str(
            source or notes or ""
        ).strip()

        observations = profile.setdefault(
            "observations",
            [],
        )

        if source_text:

            existing_observation = None

            normalized_source = (
                self._normalize(
                    source_text
                )
            )

            for observation in observations:

                if (
                    self._normalize(
                        observation.get(
                            "source",
                            "",
                        )
                    )
                    == normalized_source
                ):

                    existing_observation = (
                        observation
                    )

                    break

            if existing_observation is not None:

                existing_observation[
                    "count"
                ] = int(
                    existing_observation.get(
                        "count",
                        1,
                    )
                ) + 1

                existing_observation[
                    "last_seen"
                ] = now

            else:

                observations.append(
                    {
                        "source": source_text,
                        "first_seen": now,
                        "last_seen": now,
                        "count": 1,
                    }
                )

        interactions = max(
            1,
            int(
                profile.get(
                    "interaction_count",
                    1,
                )
            ),
        )

        profile[
            "confidence"
        ] = round(
            min(
                0.95,
                0.25
                + (
                    min(
                        interactions,
                        10,
                    )
                    * 0.06
                ),
            ),
            2,
        )

        self.data[
            "profiles"
        ][key] = profile

        self._save()

        if added_items or relationship or source_text:

            return (
                f"MEMORY SAVED: "
                f"{profile['name']} "
                f"profile updated."
            )

        return (
            f"MEMORY SAVED: "
            f"{profile['name']} profile touched."
        )

    # ================================================================
    # RETRIEVAL
    # ================================================================

    def get_person_profile(
        self,
        name: str,
    ) -> str:

        profile = self.find_profile(
            name
        )

        if profile is None:

            return (
                f"NO_PROFILE: "
                f"I do not have a persistent character "
                f"profile for '{name}'."
            )

        lines: list[str] = []

        lines.append(
            f"PERSON: {profile.get('name', name)}"
        )

        relationship = str(
            profile.get(
                "relationship",
                "",
            )
        ).strip()

        if relationship:
            lines.append(
                f"RELATIONSHIP: {relationship}"
            )

        aliases = profile.get(
            "aliases",
            [],
        )

        if aliases:
            lines.append(
                "ALIASES: "
                + ", ".join(
                    aliases
                )
            )

        for field_name, label in (
            (
                "traits",
                "TRAITS",
            ),
            (
                "preferences",
                "PREFERENCES",
            ),
            (
                "dislikes",
                "DISLIKES",
            ),
            (
                "interests",
                "INTERESTS",
            ),
            (
                "important_facts",
                "IMPORTANT FACTS",
            ),
        ):

            items = profile.get(
                field_name,
                [],
            )

            if items:

                lines.append(
                    f"{label}:"
                )

                for item in items:

                    lines.append(
                        f"- {item}"
                    )

        contradictions = profile.get(
            "contradictions",
            [],
        )

        if contradictions:

            lines.append(
                "CONTRADICTIONS / CHANGES:"
            )

            for item in contradictions:

                lines.append(
                    f"- {item}"
                )

        observations = profile.get(
            "observations",
            [],
        )

        if observations:

            lines.append(
                "RECENT OBSERVATIONS:"
            )

            for observation in observations[
                -8:
            ]:

                source = str(
                    observation.get(
                        "source",
                        "",
                    )
                ).strip()

                count = observation.get(
                    "count",
                    1,
                )

                if source:

                    lines.append(
                        f"- {source} "
                        f"(observed {count} time(s))"
                    )

        confidence = profile.get(
            "confidence",
            0.0,
        )

        lines.append(
            f"MEMORY CONFIDENCE: {confidence:.2f}"
        )

        lines.append(
            f"LAST SEEN: "
            f"{profile.get('last_seen', 'unknown')}"
        )

        return "\n".join(
            lines
        )

    def list_people(self) -> str:

        profiles = self.data.get(
            "profiles",
            {},
        )

        if not profiles:

            return (
                "NO_PROFILES: "
                "No character profiles have been created yet."
            )

        lines = [
            "KNOWN PEOPLE:"
        ]

        sorted_profiles = sorted(
            profiles.values(),
            key=lambda item: self._normalize(
                item.get(
                    "name",
                    "",
                )
            ),
        )

        for profile in sorted_profiles:

            name = profile.get(
                "name",
                "Unknown",
            )

            relationship = profile.get(
                "relationship",
                "",
            )

            confidence = float(
                profile.get(
                    "confidence",
                    0.0,
                )
            )

            if relationship:

                lines.append(
                    f"- {name} "
                    f"({relationship}, "
                    f"confidence={confidence:.2f})"
                )

            else:

                lines.append(
                    f"- {name} "
                    f"(confidence={confidence:.2f})"
                )

        return "\n".join(
            lines
        )

    # ================================================================
    # CONTEXT
    # ================================================================

    def mentioned_profiles(
        self,
        text: str,
    ) -> list[dict[str, Any]]:

        normalized_text = self._normalize(
            text
        )

        if not normalized_text:
            return []

        results: list[dict[str, Any]] = []

        for profile in self.data.get(
            "profiles",
            {},
        ).values():

            names = [
                profile.get(
                    "name",
                    "",
                )
            ]

            names.extend(
                profile.get(
                    "aliases",
                    [],
                )
            )

            for name in names:

                normalized_name = (
                    self._normalize(
                        name
                    )
                )

                if not normalized_name:
                    continue

                pattern = (
                    r"(?<!\w)"
                    + re.escape(
                        normalized_name
                    )
                    + r"(?!\w)"
                )

                if re.search(
                    pattern,
                    normalized_text,
                ):

                    if profile not in results:
                        results.append(
                            profile
                        )

                    break

        return results

    def context_for_text(
        self,
        text: str,
    ) -> str:

        profiles = self.mentioned_profiles(
            text
        )

        if not profiles:
            return ""

        blocks: list[str] = []

        for profile in profiles:

            blocks.append(
                self.get_person_profile(
                    profile.get(
                        "name",
                        "",
                    )
                )
            )

        return (
            "\n\n"
            "PERSISTENT CHARACTER MEMORY\n"
            "The following are previously learned "
            "profiles relevant to this conversation.\n"
            "Treat them as remembered observations, "
            "not absolute truth.\n\n"
            + "\n\n---\n\n".join(
                blocks
            )
        )