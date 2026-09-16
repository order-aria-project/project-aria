from __future__ import annotations

import shutil
import subprocess
from typing import Any

import psutil


def get_cpu_usage() -> str:
    """
    Return current total CPU utilisation.

    Uses psutil directly. No external hardware-monitor service
    is required.
    """
    usage = psutil.cpu_percent(
        interval=0.5
    )

    return f"{usage:.1f}%"


def get_cpu_details() -> dict[str, Any]:
    """
    Return useful CPU information without attempting
    to read CPU temperature.
    """
    return {
        "usage": get_cpu_usage(),
        "physical_cores": psutil.cpu_count(
            logical=False
        ),
        "logical_processors": psutil.cpu_count(
            logical=True
        ),
        "frequency_mhz": (
            round(
                psutil.cpu_freq().current,
                0,
            )
            if psutil.cpu_freq() is not None
            else None
        ),
    }


def get_ram_usage() -> str:
    """
    Return RAM utilisation and capacity.
    """
    memory = psutil.virtual_memory()

    used_gb = (
        memory.used
        / (1024 ** 3)
    )

    total_gb = (
        memory.total
        / (1024 ** 3)
    )

    return (
        f"{memory.percent:.1f}% "
        f"({used_gb:.1f} GB / "
        f"{total_gb:.1f} GB)"
    )


def get_ram_details() -> dict[str, Any]:
    """
    Return structured RAM information.
    """
    memory = psutil.virtual_memory()

    return {
        "usage_percent": round(
            memory.percent,
            1,
        ),
        "used_gb": round(
            memory.used / (1024 ** 3),
            2,
        ),
        "available_gb": round(
            memory.available / (1024 ** 3),
            2,
        ),
        "total_gb": round(
            memory.total / (1024 ** 3),
            2,
        ),
    }


def get_disk_space(
    drive: str = "C:\\",
) -> str:
    """
    Return free, used, and total disk capacity.
    """
    try:
        usage = shutil.disk_usage(
            drive
        )

    except OSError as exc:
        return (
            f"Disk information unavailable "
            f"for {drive}: {exc}"
        )

    total = (
        usage.total
        / (1024 ** 3)
    )

    used = (
        usage.used
        / (1024 ** 3)
    )

    free = (
        usage.free
        / (1024 ** 3)
    )

    return (
        f"{free:.1f} GB free / "
        f"{total:.1f} GB total "
        f"({used:.1f} GB used)"
    )


def get_battery() -> str:
    """
    Return battery level/status.

    Desktop systems may legitimately have no battery.
    """
    try:
        battery = (
            psutil.sensors_battery()
        )
    except Exception:
        battery = None

    if battery is None:
        return (
            "Battery information unavailable "
            "on this system."
        )

    status = (
        "charging"
        if battery.power_plugged
        else "on battery"
    )

    return (
        f"{battery.percent:.1f}% "
        f"({status})"
    )


def get_running_applications() -> list[str]:
    """
    Return unique process names currently running.
    """
    applications: set[str] = set()

    for process in psutil.process_iter(
        ["name"]
    ):
        try:
            name = process.info.get(
                "name"
            )

            if name:
                applications.add(
                    str(name)
                )

        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
        ):
            continue

    return sorted(
        applications,
        key=str.lower,
    )


def get_gpu_info() -> str:
    """
    Return NVIDIA GPU information when nvidia-smi
    is available.

    CPU temperature is deliberately not included.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,"
                "temperature.gpu,"
                "utilization.gpu,"
                "memory.used,"
                "memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            ),
            stdin=subprocess.DEVNULL,
        )

        output = result.stdout.strip()

        if not output:
            return (
                "GPU information unavailable."
            )

        parts = [
            item.strip()
            for item in output.split(",")
        ]

        if len(parts) >= 5:
            return (
                f"{parts[0]} | "
                f"{parts[1]} C | "
                f"{parts[2]}% usage | "
                f"{parts[3]} MiB / "
                f"{parts[4]} MiB VRAM"
            )

        return output

    except (
        FileNotFoundError,
        subprocess.SubprocessError,
        OSError,
    ) as exc:
        return (
            "GPU information unavailable: "
            f"{exc}"
        )


def get_system_status() -> dict[str, Any]:
    """
    Return the clean ARIA system-status snapshot.

    Deliberately excludes:
        - CPU temperature
        - Libre Hardware Monitor
        - hardware-monitor UI/service data
    """
    return {
        "cpu": get_cpu_details(),
        "ram": get_ram_details(),
        "gpu": get_gpu_info(),
        "battery": get_battery(),
        "c_drive": get_disk_space(
            "C:\\"
        ),
        "a_drive": get_disk_space(
            "A:\\"
        ),
    }