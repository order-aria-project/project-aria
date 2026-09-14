import shutil
import subprocess
from typing import Any

import psutil


def get_cpu_usage() -> str:
    """Get the current CPU usage percentage."""
    usage = psutil.cpu_percent(interval=0.5)
    return f"CPU usage: {usage:.1f}%"


def get_ram_usage() -> str:
    """Get current RAM usage and available memory."""
    memory = psutil.virtual_memory()

    used_gb = memory.used / (1024 ** 3)
    total_gb = memory.total / (1024 ** 3)
    available_gb = memory.available / (1024 ** 3)

    return (
        f"RAM usage: {memory.percent:.1f}% "
        f"({used_gb:.1f} GB / {total_gb:.1f} GB used, "
        f"{available_gb:.1f} GB available)"
    )


def get_disk_space(drive: str = "C:\\") -> str:
    """
    Get disk space information.

    Args:
        drive: Windows drive to inspect, for example C:\\ or A:\\.
    """
    try:
        usage = shutil.disk_usage(drive)
    except OSError as exc:
        return f"Could not read disk {drive}: {exc}"

    total_gb = usage.total / (1024 ** 3)
    used_gb = usage.used / (1024 ** 3)
    free_gb = usage.free / (1024 ** 3)

    return (
        f"{drive} drive: "
        f"{free_gb:.1f} GB free, "
        f"{used_gb:.1f} GB used, "
        f"{total_gb:.1f} GB total"
    )


def get_battery() -> str:
    """Get the current laptop battery status."""
    battery = psutil.sensors_battery()

    if battery is None:
        return "Battery information is unavailable."

    charging = "charging" if battery.power_plugged else "not charging"

    return (
        f"Battery: {battery.percent:.1f}% "
        f"and {charging}"
    )


def get_running_applications() -> str:
    """Get a list of visible Windows applications currently running."""
    applications: list[str] = []

    for process in psutil.process_iter(["name"]):
        try:
            name = process.info.get("name")

            if not name:
                continue

            lowered = name.lower()

            # Skip common background processes.
            if lowered in {
                "system",
                "registry",
                "svchost.exe",
                "explorer.exe",
                "dwm.exe",
                "csrss.exe",
                "wininit.exe",
                "services.exe",
                "lsass.exe",
            }:
                continue

            applications.append(name)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Remove duplicates and sort.
    unique_apps = sorted(set(applications), key=str.lower)

    if not unique_apps:
        return "No application processes could be identified."

    # Keep the result reasonably small.
    preview = unique_apps[:40]

    result = ", ".join(preview)

    if len(unique_apps) > 40:
        result += f" ... and {len(unique_apps) - 40} more."

    return f"Running applications/processes: {result}"


def get_gpu_info() -> str:
    """Get NVIDIA GPU name, temperature, utilization and VRAM usage."""
    command = [
        "nvidia-smi",
        "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return "nvidia-smi was not found. NVIDIA GPU information is unavailable."
    except subprocess.TimeoutExpired:
        return "nvidia-smi timed out while reading GPU information."
    except OSError as exc:
        return f"Could not read GPU information: {exc}"

    if result.returncode != 0:
        error = result.stderr.strip()

        if error:
            return f"nvidia-smi failed: {error}"

        return "nvidia-smi failed without providing an error message."

    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    if not lines:
        return "No NVIDIA GPU information was returned."

    gpu_results: list[str] = []

    for line in lines:
        parts = [part.strip() for part in line.split(",")]

        if len(parts) != 5:
            continue

        name, temperature, utilization, memory_used, memory_total = parts

        gpu_results.append(
            f"{name}: "
            f"{temperature}°C, "
            f"{utilization}% utilization, "
            f"{memory_used} MiB / {memory_total} MiB VRAM"
        )

    if not gpu_results:
        return "NVIDIA GPU information could not be parsed."

    return " | ".join(gpu_results)


def get_system_status() -> str:
    """Get a combined snapshot of the laptop's current hardware status."""
    cpu = get_cpu_usage()
    ram = get_ram_usage()
    gpu = get_gpu_info()
    battery = get_battery()
    system_drive = get_disk_space("C:\\")
    aria_drive = get_disk_space("A:\\")

    return "\n".join(
        [
            cpu,
            ram,
            gpu,
            battery,
            system_drive,
            aria_drive,
        ]
    )