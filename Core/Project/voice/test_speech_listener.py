from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from voice.speech_listener import SpeechListener


def main() -> None:
    print("ARIA speech-listener test")
    print()
    print("This test uses the current local Faster Whisper listener.")
    print("Speak a normal sentence.")
    print("Press Ctrl+C to stop.")
    print()

    listener = SpeechListener()

    try:
        while True:
            text = listener.listen_once()

            if text:
                print(f"HEARD > {text}", flush=True)

    except KeyboardInterrupt:
        print("\nSpeech test stopped.")

    finally:
        listener.close()


if __name__ == "__main__":
    main()
