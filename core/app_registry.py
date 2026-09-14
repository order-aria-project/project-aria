from pathlib import Path
import json


class AppRegistry:
    """Stores and retrieves installed application paths."""

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.registry_path.exists():
            self._save({})

    def _load(self) -> dict:
        try:
            with self.registry_path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save(self, data: dict) -> None:
        with self.registry_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    def register(self, name: str, executable: str) -> None:
        data = self._load()
        data[name.lower()] = executable
        self._save(data)

    def get(self, name: str) -> str | None:
        data = self._load()
        return data.get(name.lower())

    def remove(self, name: str) -> bool:
        data = self._load()

        if name.lower() not in data:
            return False

        del data[name.lower()]
        self._save(data)
        return True

    def all_apps(self) -> dict:
        return self._load()