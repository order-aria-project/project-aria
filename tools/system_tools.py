import json
import shutil
import subprocess
from typing import Any
from urllib.request import urlopen

import psutil


LHM_URL = "http://127.0.0.1:8085/data.json"


def get_cpu_usage() -> str:
    usage = psutil.cpu_percent(interval=0.5)

    return f"{usage:.1f}%"


def _load_lhm_data() -> dict[str, Any]:
    with urlopen(
        LHM_URL,
        timeout=2,
    ) as response:
        data = response.read().decode(
            "utf-8"
        )

    return json.loads(data)


def _walk_lhm_nodes(
    node: dict[str, Any],
    parents: list[str] | None = None,
):
    if parents is None:
        parents = []

    text = str(
        node.get(
            "Text",
            "",
        )
    )

    current_path = [
        *parents,
        text,
    ]

    yield node, current_path

    children = node.get(
        "Children",
        [],
    )

    if isinstance(children, list):
        for child in children:
            if isinstance(
                child,
                dict,
            ):
                yield from _walk_lhm_nodes(
                    child,
                    current_path,
                )


def _get_lhm_temperature_sensors() -> list[
    dict[str, Any]
]:
    data = _load_lhm_data()

    sensors: list[
        dict[str, Any]
    ] = []

    for node, path in _walk_lhm_nodes(data):
        sensor_type = str(
            node.get(
                "Type",
                "",
            )
        ).lower()

        sensor_name = str(
            node.get(
                "Text",
                "",
            )
        )

        if sensor_type != "temperature":
            continue

        value = node.get(
            "RawValue"
        )

        if value is None:
            value = node.get(
                "Value"
            )

        try:
            value = float(value)
        except (
            TypeError,
            ValueError,
        ):
            continue

        sensors.append(
            {
                "name": sensor_name,
                "value": value,
                "path": path,
                "sensor_id": node.get(
                    "SensorId"
                ),
            }
        )

    return sensors


def get_cpu_temperature() -> str:
    try:
        sensors = (
            _get_lhm_temperature_sensors()
        )

        if not sensors:
            return (
                "Unavailable — Libre Hardware "
                "Monitor returned no temperature sensors."
            )

        cpu_candidates: list[
            dict[str, Any]
        ] = []

        for sensor in sensors:
            path_text = " ".join(
                sensor["path"]
            ).lower()

            name_text = (
                sensor["name"]
                .lower()
            )

            # Prefer sensors associated with the CPU.
            if (
                "cpu" in path_text
                or "intel" in path_text
                or "package" in name_text
                or "core" in name_text
            ):
                cpu_candidates.append(
                    sensor
                )

        if not cpu_candidates:
            return (
                "Unavailable — no CPU temperature "
                "sensor was identified."
            )

        # Prefer Package / CPU package temperatures.
        preferred: list[
            dict[str, Any]
        ] = []

        for sensor in cpu_candidates:
            name = sensor["name"].lower()
            path = " ".join(
                sensor["path"]
            ).lower()

            if (
                "package" in name
                or "package" in path
                or "cpu package" in name
            ):
                preferred.append(
                    sensor
                )

        selected = (
            preferred[0]
            if preferred
            else cpu_candidates[0]
        )

        return (
            f"{selected['value']:.1f} °C"
        )

    except Exception as exc:
        return (
            "Unavailable — Libre Hardware "
            f"Monitor could not be read: {exc}"
        )


def get_cpu_temperature_details() -> list[
    dict[str, Any]
]:
    try:
        sensors = (
            _get_lhm_temperature_sensors()
        )

        results: list[
            dict[str, Any]
        ] = []

        for sensor in sensors:
            path_text = " ".join(
                sensor["path"]
            ).lower()

            name_text = (
                sensor["name"]
                .lower()
            )

            if (
                "cpu" in path_text
                or "intel" in path_text
                or "package" in name_text
                or "core" in name_text
            ):
                results.append(
                    sensor
                )

        return results

    except Exception:
        return []


def get_ram_usage() -> str:
    memory = psutil.virtual_memory()

    return (
        f"{memory.percent:.1f}% "
        f"({memory.used / (1024 ** 3):.1f} GB / "
        f"{memory.total / (1024 ** 3):.1f} GB)"
    )


def get_disk_space(
    drive: str = "C:\\",
) -> str:
    usage = shutil.disk_usage(
        drive
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
    battery = psutil.sensors_battery()

    if battery is None:
        return "Battery information unavailable."

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
                    name
                )

        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            continue

    return sorted(
        applications,
        key=str.lower,
    )


def get_gpu_info() -> str:
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
                f"{parts[1]} °C | "
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
            "GPU information unavailable — "
            f"{exc}"
        )


def get_system_status() -> dict[str, Any]:
    return {
        "cpu_usage": get_cpu_usage(),
        "cpu_temperature": get_cpu_temperature(),
        "ram_usage": get_ram_usage(),
        "gpu": get_gpu_info(),
        "battery": get_battery(),
        "c_drive": get_disk_space(
            "C:\\"
        ),
        "a_drive": get_disk_space(
            "A:\\"
        ),
    }