from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from voice.voice_controller import VoiceController


def handle_command(command: str) -> None:
    print()
    print(
        f"CONTROLLER RECEIVED > {command}"
    )
    print()


def main() -> None:

    controller = VoiceController(
        command_callback=handle_command
    )

    print()
    print("ARIA voice-controller test ready.")
    print()
    print("Say:")
    print("  ARIA")
    print("then:")
    print("  open Blender")
    print()
    print("Press Ctrl+C to stop.")
    print()

    try:
        controller.start()

    except KeyboardInterrupt:
        pass

    finally:
        controller.stop()


if __name__ == "__main__":
    main()