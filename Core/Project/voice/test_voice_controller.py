from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from voice.speech_listener import SpeechListener
from voice.voice_controller import VoiceController


def handle_command(command: str) -> str:
    print()
    print(f"CONTROLLER RECEIVED > {command}")
    print()
    return "I received your command."


def main() -> None:
    listener = SpeechListener()

    controller = VoiceController(
        command_callback=handle_command,
        speech_listener=listener,
    )

    print()
    print("ARIA voice-controller test ready.")
    print()
    print("Say:")
    print("  ARIA")
    print("then:")
    print("  open Blender")
    print()
    print("Guest Mode test:")
    print("  ARIA")
    print("  guest mode")
    print("  hello everyone")
    print("  ARIA mode")
    print()
    print("Press Ctrl+C to stop.")
    print()

    try:
        controller.start()

        while True:
            # Keep the test process alive until Ctrl+C.
            import time
            time.sleep(0.25)

    except KeyboardInterrupt:
        pass

    finally:
        controller.stop()
        listener.close()


if __name__ == "__main__":
    main()
