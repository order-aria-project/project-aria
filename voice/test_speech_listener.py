from pathlib import Path

from speech_listener import SpeechListener


def main() -> None:
    model_path = (
        Path(__file__).resolve().parent
        / "model"
        / "vosk-model-small-en-us-0.15"
    )

    print(
        "Loading ARIA's local speech model..."
    )

    listener = SpeechListener(
        model_path=model_path
    )

    print()
    print(
        "Speak a sentence."
    )
    print(
        "Press Ctrl+C to stop."
    )
    print()

    try:
        while True:
            text = listener.listen_once()

            if text:
                print(
                    f"HEARD > {text}"
                )

    except KeyboardInterrupt:
        print(
            "\nSpeech test stopped."
        )

    finally:
        listener.close()


if __name__ == "__main__":
    main()