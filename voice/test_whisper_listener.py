from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from voice.speech_listener import SpeechListener


def main() -> None:
    listener = SpeechListener(
        listen_seconds=5.0,
    )

    print()
    print("Whisper voice test ready.")
    print("Speak a normal ARIA command.")
    print("Example: open Blender")
    print("Press Ctrl+C to stop.")
    print()

    try:
        while True:
            text = listener.listen_once()

            if text:
                print(f"HEARD > {text}")

    except KeyboardInterrupt:
        print("\nWhisper test stopped.")

    finally:
        listener.close()


if __name__ == "__main__":
    main()