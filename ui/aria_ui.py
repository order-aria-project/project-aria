from __future__ import annotations

import queue
import tkinter as tk
from datetime import datetime
from typing import Any


class ARIAUI:
    BG = "#080c11"
    PANEL = "#111820"
    PANEL_ALT = "#151e27"
    BORDER = "#24303b"
    TEXT = "#eef4f8"
    MUTED = "#7f8d9c"
    GREEN = "#5be49b"
    YELLOW = "#f5c76a"
    RED = "#ff6b6b"
    BLUE = "#61a8ff"

    def __init__(
        self,
        system_tools: Any,
    ) -> None:
        self.system_tools = system_tools

        self.root = tk.Tk()
        self.root.withdraw()

        self.running = True

        self._requests: queue.Queue[
            tuple[str, dict[str, Any]]
        ] = queue.Queue()

        self._windows: list[
            tk.Toplevel
        ] = []

        self.root.after(
            50,
            self._process_requests,
        )

    def request_panel(
        self,
        panel_name: str,
        **kwargs: Any,
    ) -> str:
        self._requests.put(
            (
                panel_name,
                kwargs,
            )
        )

        return (
            f"UI_REQUESTED; panel={panel_name}"
        )

    def run(self) -> None:
        self.root.mainloop()

    def shutdown(self) -> None:
        if not self.running:
            return

        self.running = False

        for window in list(
            self._windows
        ):
            try:
                window.destroy()
            except tk.TclError:
                pass

        self._windows.clear()

        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _process_requests(self) -> None:
        if not self.running:
            return

        while True:
            try:
                panel_name, kwargs = (
                    self._requests.get_nowait()
                )
            except queue.Empty:
                break

            try:
                self._open_panel(
                    panel_name,
                    **kwargs,
                )
            except Exception as exc:
                print(
                    f"[UI ERROR] {panel_name}: {exc}"
                )

        self.root.after(
            50,
            self._process_requests,
        )

    def _open_panel(
        self,
        panel_name: str,
        **kwargs: Any,
    ) -> None:
        panel_name = (
            panel_name.strip().lower()
        )

        if panel_name == "overview":
            self._open_overview()
            return

        if panel_name == "cpu":
            self._open_cpu()
            return

        if panel_name == "gpu":
            self._open_gpu()
            return

        if panel_name == "ram":
            self._open_ram()
            return

    # ============================================================
    # Window helpers
    # ============================================================

    def _window(
        self,
        title: str,
        width: int,
        height: int,
    ) -> tk.Toplevel:
        window = tk.Toplevel(
            self.root
        )

        window.title(
            f"A.R.I.A. — {title}"
        )

        window.geometry(
            f"{width}x{height}"
        )

        window.minsize(
            850,
            550,
        )

        window.configure(
            bg=self.BG
        )

        window.deiconify()
        window.lift()
        window.focus_force()

        self._windows.append(
            window
        )

        def close() -> None:
            try:
                self._windows.remove(
                    window
                )
            except ValueError:
                pass

            try:
                window.destroy()
            except tk.TclError:
                pass

        window.protocol(
            "WM_DELETE_WINDOW",
            close,
        )

        return window

    def _header(
        self,
        window: tk.Toplevel,
        title: str,
        subtitle: str,
    ) -> None:
        frame = tk.Frame(
            window,
            bg=self.BG,
        )

        frame.pack(
            fill="x",
            padx=30,
            pady=(25, 5),
        )

        tk.Label(
            frame,
            text=title,
            bg=self.BG,
            fg=self.TEXT,
            font=(
                "Segoe UI",
                26,
                "bold",
            ),
        ).pack(
            anchor="w"
        )

        tk.Label(
            frame,
            text=subtitle,
            bg=self.BG,
            fg=self.MUTED,
            font=(
                "Segoe UI",
                10,
            ),
        ).pack(
            anchor="w",
            pady=(3, 0),
        )

    def _card(
        self,
        parent: tk.Widget,
    ) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=self.PANEL,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )

    def _metric(
        self,
        parent: tk.Widget,
        title: str,
        value: str,
        subtitle: str = "",
    ) -> tk.Frame:
        card = self._card(
            parent
        )

        tk.Label(
            card,
            text=title,
            bg=self.PANEL,
            fg=self.MUTED,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w",
            padx=16,
            pady=(14, 3),
        )

        tk.Label(
            card,
            text=value,
            bg=self.PANEL,
            fg=self.TEXT,
            font=(
                "Segoe UI",
                16,
                "bold",
            ),
            justify="left",
            anchor="w",
            wraplength=320,
        ).pack(
            anchor="w",
            padx=16,
        )

        if subtitle:
            tk.Label(
                card,
                text=subtitle,
                bg=self.PANEL,
                fg=self.MUTED,
                font=(
                    "Segoe UI",
                    8,
                ),
            ).pack(
                anchor="w",
                padx=16,
                pady=(3, 14),
            )

        return card

    # ============================================================
    # OVERVIEW
    # ============================================================

    def _open_overview(self) -> None:
        window = self._window(
            "System Overview",
            1200,
            760,
        )

        self._header(
            window,
            "SYSTEM OVERVIEW",
            "Complete A.R.I.A. system state",
        )

        root = tk.Frame(
            window,
            bg=self.BG,
        )

        root.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=20,
        )

        # Top row
        top = tk.Frame(
            root,
            bg=self.BG,
        )

        top.pack(
            fill="x"
        )

        top.columnconfigure(
            0,
            weight=1,
        )

        top.columnconfigure(
            1,
            weight=1,
        )

        top.columnconfigure(
            2,
            weight=1,
        )

        cpu = self.system_tools.get_cpu_usage()
        temp = self.system_tools.get_cpu_temperature()
        ram = self.system_tools.get_ram_usage()

        self._metric(
            top,
            "CPU",
            cpu,
            "Processor usage",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )

        self._metric(
            top,
            "CPU TEMPERATURE",
            temp,
            "Live CPU temperature",
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=6,
        )

        self._metric(
            top,
            "RAM",
            ram,
            "Memory usage",
        ).grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(6, 0),
        )

        # Bottom
        bottom = tk.Frame(
            root,
            bg=self.BG,
        )

        bottom.pack(
            fill="both",
            expand=True,
            pady=(12, 0),
        )

        bottom.columnconfigure(
            0,
            weight=1,
        )

        bottom.columnconfigure(
            1,
            weight=1,
        )

        bottom.rowconfigure(
            0,
            weight=1,
        )

        # GPU
        gpu_card = self._card(
            bottom
        )

        gpu_card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 6),
        )

        tk.Label(
            gpu_card,
            text="GPU",
            bg=self.PANEL,
            fg=self.MUTED,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w",
            padx=16,
            pady=(16, 8),
        )

        tk.Label(
            gpu_card,
            text=self.system_tools.get_gpu_info(),
            bg=self.PANEL,
            fg=self.TEXT,
            font=(
                "Segoe UI",
                12,
                "bold",
            ),
            justify="left",
            anchor="nw",
            wraplength=480,
        ).pack(
            fill="both",
            expand=True,
            padx=16,
            pady=(0, 16),
        )

        # Right
        right = tk.Frame(
            bottom,
            bg=self.BG,
        )

        right.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(6, 0),
        )

        right.columnconfigure(
            0,
            weight=1,
        )

        right.columnconfigure(
            1,
            weight=1,
        )

        right.rowconfigure(
            2,
            weight=1,
        )

        self._metric(
            right,
            "BATTERY",
            self.system_tools.get_battery(),
            "Power state",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
            pady=(0, 8),
        )

        self._metric(
            right,
            "C: DRIVE",
            self.system_tools.get_disk_space(
                "C:\\"
            ),
            "System storage",
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(4, 0),
            pady=(0, 8),
        )

        self._metric(
            right,
            "A: DRIVE",
            self.system_tools.get_disk_space(
                "A:\\"
            ),
            "ARIA storage",
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 8),
        )

        apps = self._card(
            right
        )

        apps.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
        )

        tk.Label(
            apps,
            text="RUNNING APPLICATIONS",
            bg=self.PANEL,
            fg=self.MUTED,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w",
            padx=16,
            pady=(14, 6),
        )

        text = tk.Text(
            apps,
            bg=self.PANEL,
            fg=self.TEXT,
            relief="flat",
            borderwidth=0,
            font=(
                "Consolas",
                9,
            ),
            state="normal",
        )

        text.pack(
            fill="both",
            expand=True,
            padx=16,
            pady=(0, 16),
        )

        for app in self.system_tools.get_running_applications():
            text.insert(
                tk.END,
                f"● {app}\n",
            )

        text.configure(
            state="disabled"
        )

        tk.Label(
            root,
            text=(
                "A.R.I.A. • "
                + datetime.now().strftime(
                    "%H:%M:%S"
                )
            ),
            bg=self.BG,
            fg=self.MUTED,
            font=(
                "Segoe UI",
                8,
            ),
        ).pack(
            anchor="w",
            pady=(10, 0),
        )

    # ============================================================
    # CPU
    # ============================================================

    def _open_cpu(self) -> None:
        window = self._window(
            "CPU Monitor",
            1000,
            700,
        )

        self._header(
            window,
            "CPU MONITOR",
            "Live processor telemetry",
        )

        root = tk.Frame(
            window,
            bg=self.BG,
        )

        root.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=20,
        )

        root.columnconfigure(
            0,
            weight=1,
        )

        root.columnconfigure(
            1,
            weight=2,
        )

        root.rowconfigure(
            0,
            weight=1,
        )

        left = self._card(
            root
        )

        left.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 10),
        )

        right = self._card(
            root
        )

        right.grid(
            row=0,
            column=1,
            sticky="nsew",
        )

        tk.Label(
            left,
            text="CPU TEMPERATURE",
            bg=self.PANEL,
            fg=self.MUTED,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            pady=(24, 10)
        )

        self.temperature_canvas = tk.Canvas(
            left,
            width=300,
            height=300,
            bg=self.PANEL,
            highlightthickness=0,
        )

        self.temperature_canvas.pack()

        self.temperature_value = tk.Label(
            left,
            text="-- °C",
            bg=self.PANEL,
            fg=self.TEXT,
            font=(
                "Segoe UI",
                32,
                "bold",
            ),
        )

        self.temperature_value.place(
            relx=0.5,
            rely=0.44,
            anchor="center",
        )

        self.temperature_status = tk.Label(
            left,
            text="READING...",
            bg=self.PANEL,
            fg=self.MUTED,
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        )

        self.temperature_status.pack(
            pady=12
        )

        self._cpu_sensor_update()

        tk.Label(
            right,
            text="TEMPERATURE HISTORY",
            bg=self.PANEL,
            fg=self.MUTED,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w",
            padx=16,
            pady=(18, 6),
        )

        self.graph = tk.Canvas(
            right,
            bg=self.PANEL,
            highlightthickness=0,
        )

        self.graph.pack(
            fill="both",
            expand=True,
            padx=16,
            pady=(0, 16),
        )

        self.history: list[
            float
        ] = []

    def _cpu_sensor_update(self) -> None:
        if not self.running:
            return

        try:
            value = (
                self.system_tools.get_cpu_temperature()
            )

            usage = (
                self.system_tools.get_cpu_usage()
            )

            if value.startswith(
                "Unavailable"
            ):
                self.temperature_value.config(
                    text="-- °C"
                )

                self.temperature_status.config(
                    text="SENSOR UNAVAILABLE",
                    fg=self.MUTED,
                )
            else:
                temperature = float(
                    value.replace(
                        "°C",
                        "",
                    ).strip()
                )

                self.temperature_value.config(
                    text=f"{temperature:.1f} °C"
                )

                state, color = (
                    self._temperature_status(
                        temperature
                    )
                )

                self.temperature_status.config(
                    text=f"{state} • CPU {usage}",
                    fg=color,
                )

                self.history.append(
                    temperature
                )

                if len(
                    self.history
                ) > 60:
                    self.history.pop(
                        0
                    )

                self._draw_graph()

        except Exception:
            self.temperature_value.config(
                text="-- °C"
            )

        self.root.after(
            1500,
            self._cpu_sensor_update,
        )

    def _draw_graph(self) -> None:
        canvas = self.graph

        canvas.delete(
            "all"
        )

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 150 or height < 100:
            return

        if not self.history:
            return

        left = 10
        right = width - 10
        top = 15
        bottom = height - 20

        points: list[float] = []

        minimum = 20.0
        maximum = 100.0

        count = len(
            self.history
        )

        for index, value in enumerate(
            self.history
        ):
            x = (
                left
                if count == 1
                else left
                + (right - left)
                * index
                / (count - 1)
            )

            normalized = (
                value - minimum
            ) / (
                maximum - minimum
            )

            normalized = max(
                0,
                min(
                    1,
                    normalized,
                ),
            )

            y = (
                bottom
                - (
                    bottom - top
                )
                * normalized
            )

            points.extend(
                [x, y]
            )

        if len(points) >= 4:
            color = self._temperature_color(
                self.history[-1]
            )

            canvas.create_line(
                *points,
                fill=color,
                width=3,
                smooth=True,
            )

    # ============================================================
    # OTHER PANELS
    # ============================================================

    def _open_gpu(self) -> None:
        window = self._window(
            "GPU Monitor",
            900,
            600,
        )

        self._header(
            window,
            "GPU MONITOR",
            "Graphics processor telemetry",
        )

        card = self._card(
            window
        )

        card.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=20,
        )

        tk.Label(
            card,
            text=self.system_tools.get_gpu_info(),
            bg=self.PANEL,
            fg=self.TEXT,
            font=(
                "Segoe UI",
                16,
                "bold",
            ),
            justify="left",
        ).pack(
            padx=20,
            pady=30,
        )

    def _open_ram(self) -> None:
        window = self._window(
            "Memory Monitor",
            800,
            500,
        )

        self._header(
            window,
            "MEMORY MONITOR",
            "System memory telemetry",
        )

        card = self._card(
            window
        )

        card.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=20,
        )

        tk.Label(
            card,
            text=self.system_tools.get_ram_usage(),
            bg=self.PANEL,
            fg=self.TEXT,
            font=(
                "Segoe UI",
                26,
                "bold",
            ),
        ).pack(
            pady=40
        )

    # ============================================================
    # HELPERS
    # ============================================================

    @classmethod
    def _temperature_status(
        cls,
        temperature: float,
    ) -> tuple[str, str]:
        if temperature < 65:
            return (
                "NORMAL",
                cls.GREEN,
            )

        if temperature < 80:
            return (
                "ELEVATED",
                cls.YELLOW,
            )

        return (
            "HIGH",
            cls.RED,
        )

    @classmethod
    def _temperature_color(
        cls,
        temperature: float,
    ) -> str:
        return cls._temperature_status(
            temperature
        )[1]