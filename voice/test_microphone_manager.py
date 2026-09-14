from microphone_manager import MicrophoneManager


def main() -> None:
    manager = MicrophoneManager()

    print("ARIA microphone test")
    print()

    print("Available microphones:")

    for device in manager.list_devices():
        print(
            f"  [{device.index}] {device.name}"
        )

    print()

    print("Selecting a working microphone...")

    try:
        device = manager.get_working_device()

        print(
            f"Selected: {device.name}"
        )

        print(
            f"Device index: {device.index}"
        )

        print(
            "Microphone is working."
        )

    except Exception as exc:
        print(
            f"Microphone test failed: {exc}"
        )


if __name__ == "__main__":
    main()