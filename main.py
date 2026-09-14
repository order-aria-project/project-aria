from pathlib import Path
from datetime import datetime
import json


# -----------------------------
# ARIA FILE LOCATIONS
# -----------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
PROFILE_PATH = PROJECT_ROOT / "core" / "aria_profile.json"
LOG_PATH = Path(r"A:\Logs\mission.log")


# -----------------------------
# MISSION LOGGER
# -----------------------------

def log_event(message: str) -> None:
    """Write an event to ARIA's Mission Log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


# -----------------------------
# LOAD ARIA PROFILE
# -----------------------------

def load_profile() -> dict:
    try:
        with PROFILE_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)

    except FileNotFoundError:
        raise SystemExit(
            f"ARIA profile not found: {PROFILE_PATH}"
        )

    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"ARIA profile is invalid JSON: {exc}"
        )


# -----------------------------
# MAIN PROGRAM
# -----------------------------

def main() -> None:
    aria = load_profile()

    log_event("CORE INITIALIZED")

    print("=" * 50)
    print(f"{aria['name']} — {aria['version']}")
    print(f"Meaning: {aria['meaning']}")
    print(f"Owner: {aria['owner']}")
    print("CORE ONLINE")
    print("=" * 50)

    while True:
        try:
            command = input("You: ").strip()

        except (KeyboardInterrupt, EOFError):
            log_event("CORE SHUTDOWN")
            print("\nARIA: Goodbye, Beau.")
            break

        if not command:
            continue

        log_event(f"USER: {command}")

        if command.lower() in {"exit", "quit"}:
            log_event("CORE SHUTDOWN")
            print("ARIA: Goodbye, Beau.")
            break

        if command.lower() == "hello":
            response = "Hello, Beau."

        else:
            response = f"I heard you say: {command}"

        print(f"ARIA: {response}")
        log_event(f"ARIA: {response}")


if __name__ == "__main__":
    main()