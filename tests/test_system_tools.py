from tools.system_tools import (
    get_cpu_usage,
    get_ram_usage,
    get_gpu_info,
    get_disk_space,
    get_battery,
    get_running_applications,
    get_system_status,
)


def main() -> None:
    print("=" * 60)
    print("ARIA SYSTEM TOOLS TEST")
    print("=" * 60)

    print()
    print("CPU:")
    print(get_cpu_usage())

    print()
    print("RAM:")
    print(get_ram_usage())

    print()
    print("GPU:")
    print(get_gpu_info())

    print()
    print("Battery:")
    print(get_battery())

    print()
    print("System drive:")
    print(get_disk_space("C:\\"))

    print()
    print("ARIA drive:")
    print(get_disk_space("A:\\"))

    print()
    print("Running applications:")
    print(get_running_applications())

    print()
    print("Combined status:")
    print(get_system_status())


if __name__ == "__main__":
    main()