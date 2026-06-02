from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from app.core import (
    ElectrochemistryController,
    MeasurementManager,
    MeasurementMode,
    MeasurementParameters,
    build_device,
    format_charge,
    format_current,
    format_voltage,
    save_measurement_csv,
    safe_resource_name,
)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class ElectrochemistryApp:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = load_json(config_path)
        self.root = tk.Tk()
        self.root.title(self.config.get("ui", {}).get("window_title", "Electrochemistry Control App"))
        self.root.geometry("1200x800")

        self.controller: ElectrochemistryController | None = None
        self.manager: MeasurementManager | None = None

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self.connection_frame = ttk.LabelFrame(self.root, text="Connection", padding=10)
        self.connection_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.connection_frame.columnconfigure(1, weight=1)

        self.simulation_var = tk.BooleanVar(value=self.config.get("device", {}).get("mode", "simulation") == "simulation")
        self.resource_var = tk.StringVar(value=self.config.get("device", {}).get("resource_name", "GPIB0::1::INSTR"))
        self.connection_status_var = tk.StringVar(value="未接続")
        self.idn_var = tk.StringVar(value="")

        ttk.Checkbutton(self.connection_frame, text="Simulation", variable=self.simulation_var).grid(row=0, column=0, sticky="w")
        ttk.Label(self.connection_frame, text="GPIB Address / Resource").grid(row=1, column=0, sticky="w")
        ttk.Entry(self.connection_frame, textvariable=self.resource_var).grid(row=1, column=1, sticky="ew")
        ttk.Button(self.connection_frame, text="Connect", command=self.connect_device).grid(row=2, column=0, pady=5, sticky="ew")
        ttk.Button(self.connection_frame, text="Disconnect", command=self.disconnect_device).grid(row=2, column=1, pady=5, sticky="ew")
        ttk.Label(self.connection_frame, textvariable=self.connection_status_var).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(self.connection_frame, textvariable=self.idn_var).grid(row=4, column=0, columnspan=2, sticky="w")

        self.measurement_frame = ttk.LabelFrame(self.root, text="Measurement", padding=10)
        self.measurement_frame.grid(row=1, column=0, sticky="nsew", padx=10)
        self.measurement_frame.columnconfigure(1, weight=1)

        self.mode_var = tk.StringVar(value=self.config.get("measurement", {}).get("mode", "constant_current"))
        self.sample_interval_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("sample_interval_s", 1.0)))
        self.max_duration_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("max_duration_s", 3600.0)))
        self.current_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("current_a", 0.01)))
        self.voltage_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("voltage_v", 1.0)))
        self.current_limit_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("current_limit_a", 1.0)))
        self.voltage_limit_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("voltage_limit_v", 10.0)))
        self.scan_start_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("scan_start_v", -1.0)))
        self.scan_stop_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("scan_stop_v", 1.0)))
        self.scan_rate_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("scan_rate_v_per_s", 0.1)))
        self.cycles_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("cycles", 1)))
        self.mass_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("mass_g", 1.0)))
        self.formula_var = tk.StringVar(value=self.config.get("measurement", {}).get("formula", "LiFePO4"))
        self.electrons_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("electrons", 1)))
        self.efficiency_var = tk.StringVar(value=str(self.config.get("measurement", {}).get("charge_efficiency", 1.0)))
        self.target_charge_var = tk.StringVar(value="0 C")

        row = 0
        entries = [
            ("Mode", self.mode_var),
            ("Sample interval (s)", self.sample_interval_var),
            ("Max duration (s)", self.max_duration_var),
            ("Current (A)", self.current_var),
            ("Voltage (V)", self.voltage_var),
            ("Current limit (A)", self.current_limit_var),
            ("Voltage limit (V)", self.voltage_limit_var),
            ("CV start (V)", self.scan_start_var),
            ("CV stop (V)", self.scan_stop_var),
            ("CV rate (V/s)", self.scan_rate_var),
            ("CV cycles", self.cycles_var),
            ("Mass (g)", self.mass_var),
            ("Formula", self.formula_var),
            ("Electrons", self.electrons_var),
            ("Efficiency", self.efficiency_var),
        ]
        ttk.Combobox(self.measurement_frame, textvariable=self.mode_var, values=[m.value for m in MeasurementMode], state="readonly").grid(row=row, column=1, sticky="ew")
        ttk.Label(self.measurement_frame, text="Mode").grid(row=row, column=0, sticky="w")
        row += 1
        for label, var in entries[1:]:
            ttk.Label(self.measurement_frame, text=label).grid(row=row, column=0, sticky="w")
            ttk.Entry(self.measurement_frame, textvariable=var).grid(row=row, column=1, sticky="ew")
            row += 1
        ttk.Label(self.measurement_frame, text="Target charge").grid(row=row, column=0, sticky="w")
        ttk.Label(self.measurement_frame, textvariable=self.target_charge_var).grid(row=row, column=1, sticky="w")
        row += 1
        ttk.Button(self.measurement_frame, text="Start", command=self.start_measurement).grid(row=row, column=0, pady=5, sticky="ew")
        ttk.Button(self.measurement_frame, text="Stop", command=self.stop_measurement).grid(row=row, column=1, pady=5, sticky="ew")

        self.status_frame = ttk.LabelFrame(self.root, text="Status", padding=10)
        self.status_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.status_frame.columnconfigure(1, weight=1)
        self.message_var = tk.StringVar(value="Ready")
        self.voltage_status_var = tk.StringVar(value="0 V")
        self.current_status_var = tk.StringVar(value="0 A")
        self.charge_status_var = tk.StringVar(value="0 C")
        self.elapsed_status_var = tk.StringVar(value="0 s")
        for index, (label, var) in enumerate([
            ("Message", self.message_var),
            ("Voltage", self.voltage_status_var),
            ("Current", self.current_status_var),
            ("Charge", self.charge_status_var),
            ("Elapsed", self.elapsed_status_var),
        ]):
            ttk.Label(self.status_frame, text=label).grid(row=index, column=0, sticky="w")
            ttk.Label(self.status_frame, textvariable=var).grid(row=index, column=1, sticky="w")

        self.plot_frame = ttk.LabelFrame(self.root, text="Live Plot", padding=10)
        self.plot_frame.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=(0, 10), pady=(0, 10))
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(1, weight=1)

        self.figure = Figure(figsize=(7, 5), dpi=100)
        self.axis = self.figure.add_subplot(111)
        self.axis.grid(True, alpha=0.3)
        self.axis.set_xlabel("Time (s)")
        self.axis.set_ylabel("Voltage (V)")
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.draw_idle()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_events()
        self._refresh_target_charge()

    def connect_device(self) -> None:
        device_config = self.config.setdefault("device", {})
        device_config["mode"] = "simulation" if self.simulation_var.get() else "gpib"
        device_config["resource_name"] = self.resource_var.get().strip()
        self.controller = ElectrochemistryController(build_device(device_config))
        try:
            state = self.controller.connect(self.resource_var.get().strip() or device_config["resource_name"])
            self.manager = MeasurementManager(self.controller)
            self.connection_status_var.set("接続済み")
            self.idn_var.set(state.idn)
            self.message_var.set(f"Connected: {state.idn}")
        except Exception as exc:
            messagebox.showerror("接続エラー", str(exc))
            self.connection_status_var.set("接続失敗")
            self.message_var.set(str(exc))

    def disconnect_device(self) -> None:
        if self.manager is not None:
            self.manager.stop()
        if self.controller is not None:
            self.controller.disconnect()
        self.connection_status_var.set("未接続")
        self.idn_var.set("")
        self.message_var.set("Disconnected")

    def _refresh_target_charge(self) -> None:
        try:
            params = MeasurementParameters(
                mass_g=float(self.mass_var.get()),
                formula=self.formula_var.get(),
                electrons=int(float(self.electrons_var.get())),
                charge_efficiency=float(self.efficiency_var.get()),
            )
            self.target_charge_var.set(format_charge(params.compute_target_charge()))
        except Exception as exc:
            self.target_charge_var.set(str(exc))

    def build_parameters(self) -> MeasurementParameters:
        params = MeasurementParameters(
            mode=MeasurementMode(self.mode_var.get()),
            sample_interval_s=float(self.sample_interval_var.get()),
                max_duration_s=float(self.max_duration_var.get()),
            current_a=float(self.current_var.get()),
            voltage_v=float(self.voltage_var.get()),
            current_limit_a=float(self.current_limit_var.get()),
            voltage_limit_v=float(self.voltage_limit_var.get()),
            scan_start_v=float(self.scan_start_var.get()),
            scan_stop_v=float(self.scan_stop_var.get()),
            scan_rate_v_per_s=float(self.scan_rate_var.get()),
            cycles=int(float(self.cycles_var.get())),
            mass_g=float(self.mass_var.get()),
            formula=self.formula_var.get(),
            electrons=int(float(self.electrons_var.get())),
            charge_efficiency=float(self.efficiency_var.get()),
        )
        params.compute_target_charge()
        return params

    def start_measurement(self) -> None:
        if self.manager is None:
            messagebox.showwarning("未接続", "先に接続してください")
            return
        try:
            self._refresh_target_charge()
            params = self.build_parameters()
            self.axis.clear()
            self.axis.grid(True, alpha=0.3)
            self.manager.start(params)
            self.message_var.set("Measurement started")
        except Exception as exc:
            messagebox.showerror("測定エラー", str(exc))

    def stop_measurement(self) -> None:
        if self.manager is not None:
            self.manager.stop()

    def _poll_events(self) -> None:
        if self.manager is not None:
            while True:
                try:
                    event = self.manager.events.get_nowait()
                except Exception:
                    break
                self._handle_event(event.kind, event.payload)
        self.root.after(100, self._poll_events)

    def _handle_event(self, kind: str, payload: dict) -> None:
        if kind == "point":
            point = payload["point"]
            self.voltage_status_var.set(format_voltage(point.voltage_v))
            self.current_status_var.set(format_current(point.current_a))
            self.charge_status_var.set(format_charge(point.charge_c))
            self.elapsed_status_var.set(f"{point.time_s:.2f} s")
            self._update_plot()
        elif kind == "status":
            self.message_var.set(payload.get("message", ""))
        elif kind == "finished":
            self.message_var.set(f"Finished: {payload.get('reason', '')}")
        elif kind == "error":
            self.message_var.set(payload.get("message", ""))
            messagebox.showerror("測定エラー", payload.get("message", "Unknown error"))

    def _update_plot(self) -> None:
        if self.manager is None:
            return
        result = self.manager.result
        mode = result.mode
        self.axis.clear()
        self.axis.grid(True, alpha=0.3)
        if mode == MeasurementMode.CV.value:
            self.axis.set_xlabel("Voltage (V)")
            self.axis.set_ylabel("Current (A)")
            self.axis.plot(result.voltage_v, result.current_a, color="#c0392b", linewidth=1.5)
        elif mode == MeasurementMode.CONSTANT_VOLTAGE.value:
            self.axis.set_xlabel("Time (s)")
            self.axis.set_ylabel("Current (A)")
            self.axis.plot(result.time_s, result.current_a, color="#2980b9", linewidth=1.5)
        else:
            self.axis.set_xlabel("Time (s)")
            self.axis.set_ylabel("Voltage (V)")
            self.axis.plot(result.time_s, result.voltage_v, color="#16a085", linewidth=1.5)
        self.canvas.draw_idle()

    def close(self) -> None:
        try:
            self.disconnect_device()
            save_json(self.config_path, self.config)
        finally:
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()