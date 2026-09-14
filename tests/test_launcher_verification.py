from pathlib import Path

from core.app_registry import AppRegistry
from automation.app_launcher import ApplicationLauncher


def main() -> None:
    registry = AppRegistry(
        Path(
            "A:/Core/Project/config/applications.json"
        )
    )

    launcher = ApplicationLauncher(registry)

    print("Testing Blender launch verification...")
    print()

    result = launcher.launch("Blender")

    print(result)


if __name__ == "__main__":
    main()