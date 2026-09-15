from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from voice.wake_word_listener import WakeWordListener


def main() -> None:

    listener = WakeWordListener()

    print()
    print("ARIA persistent wake-word test ready.")
    print("Say: ARIA")
    print("Press Ctrl+C to stop.")
    print()

    try:

        while True:

            if listener.listen_once():
                print(
                    "WAKE > ARIA detected!"
                )

    except KeyboardInterrupt:

        print(
            "\nWake-word test stopped."
        )

    finally:

        listener.close()


if __name__ == "__main__":
    main()