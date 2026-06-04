from __future__ import annotations

import json
import time
import tkinter as tk
from enum import Enum
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from app.core import (
    ElectrochemistryController,
    MeasurementManager,
    MeasurementMode,
    MeasurementParameters,
    build_device,
    charge_from_mass_formula,
    format_charge,
    format_current,
    format_voltage,
    save_measurement_csv,
)


# ──────────────────────────────────────────────────────────────────────────────

class StopCondition(str, Enum):
    TIME = "time"
    CHARGE_COMPUTED = "charge_computed"
    CHARGE_MANUAL = "charge_manual"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class _ScrollableFrame(ttk.Frame):
    """縦スクロール可能なフレーム。inner にウィジェットを配置する。"""

    def __init__(self, parent: tk.Widget, **kw):
        super().__init__(parent, **kw)
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self.inner = ttk.Frame(self._canvas)
        self._win_id = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._vsb.set)
        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._vsb.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._canvas.bind("<Enter>", lambda _: self._canvas.bind_all("<MouseWheel>", self._on_mw))
        self._canvas.bind("<Leave>", lambda _: self._canvas.unbind_all("<MouseWheel>"))

    def _on_inner_configure(self, _e):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._win_id, width=e.width)

    def _on_mw(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")


# ──────────────────────────────────────────────────────────────────────────────

class ElectrochemistryApp:

    # モードごとに表示するパラメータキーセット
    _MODE_PARAMS: dict[MeasurementMode, set[str]] = {
        MeasurementMode.CONSTANT_CURRENT: {
            "sample_interval", "max_duration", "current", "current_limit", "voltage_limit",
        },
        MeasurementMode.CONSTANT_VOLTAGE: {
            "sample_interval", "max_duration", "voltage", "current_limit", "voltage_limit",
        },
        MeasurementMode.CV: {
            "sample_interval", "scan_start", "scan_stop", "scan_rate", "cycles",
            "current_limit", "voltage_limit",
        },
    }

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = load_json(config_path)
        self.controller: ElectrochemistryController | None = None
        self.manager: MeasurementManager | None = None

        self.root = tk.Tk()
        self.root.title(self.config.get("ui", {}).get("window_title", "Electrochemistry Control App"))
        self.root.geometry("1100x680")
        self.root.minsize(900, 580)

        # 左パネル固定幅 / 右パネル可変
        self.root.columnconfigure(0, weight=0, minsize=310)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root)
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        self._build_connection_frame(left)
        self._build_parameter_frame(left)
        self._build_status_frame(left)
        self._build_plot_frame(self.root)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.on_mode_change()
        self._refresh_target_charge()
        self._poll_events()

    # ── Connection ─────────────────────────────────────────────────────────────

    def _build_connection_frame(self, parent: ttk.Frame) -> None:
        frm = ttk.LabelFrame(parent, text="Connection", padding=6)
        frm.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        frm.columnconfigure(1, weight=1)

        m = self.config.get("device", {})
        self.simulation_var = tk.BooleanVar(value=m.get("mode", "simulation") == "simulation")
        self.resource_var = tk.StringVar(value=m.get("resource_name", "GPIB0::19::INSTR"))
        self.connection_status_var = tk.StringVar(value="未接続")
        self.idn_var = tk.StringVar()

        ttk.Checkbutton(frm, text="Simulation mode", variable=self.simulation_var).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frm, text="GPIB Resource").grid(row=1, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(frm, textvariable=self.resource_var).grid(row=1, column=1, sticky="ew")
        ttk.Button(frm, text="Connect", command=self.connect_device).grid(
            row=2, column=0, sticky="ew", pady=4, padx=(0, 2))
        ttk.Button(frm, text="Disconnect", command=self.disconnect_device).grid(
            row=2, column=1, sticky="ew", pady=4)
        ttk.Label(frm, textvariable=self.connection_status_var).grid(
            row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(frm, textvariable=self.idn_var, foreground="gray").grid(
            row=4, column=0, columnspan=2, sticky="w")

    # ── Measurement parameters ─────────────────────────────────────────────────

    def _build_parameter_frame(self, parent: ttk.Frame) -> None:
        outer = ttk.LabelFrame(parent, text="Measurement Parameters", padding=4)
        outer.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        sf = _ScrollableFrame(outer)
        sf.grid(row=0, column=0, sticky="nsew")
        g = sf.inner  # 配置先
        g.columnconfigure(1, weight=1)

        cfg = self.config.get("measurement", {})

        # StringVars ────────────────────────────────────────────────────────────
        self.mode_var = tk.StringVar(value=cfg.get("mode", MeasurementMode.CONSTANT_CURRENT.value))
        self.sample_interval_var = tk.StringVar(value=str(cfg.get("sample_interval_s", 1.0)))
        self.max_duration_var = tk.StringVar(value=str(cfg.get("max_duration_s", 3600.0)))
        self.current_var = tk.StringVar(value=str(cfg.get("current_a", 0.01) * 1000))   # mA
        self.voltage_var = tk.StringVar(value=str(cfg.get("voltage_v", 1.0)))
        self.current_limit_var = tk.StringVar(value=str(cfg.get("current_limit_a", 1.0) * 1000))  # mA
        self.voltage_limit_var = tk.StringVar(value=str(cfg.get("voltage_limit_v", 10.0)))
        self.scan_start_var = tk.StringVar(value=str(cfg.get("scan_start_v", -1.0)))
        self.scan_stop_var = tk.StringVar(value=str(cfg.get("scan_stop_v", 1.0)))
        self.scan_rate_var = tk.StringVar(value=str(cfg.get("scan_rate_v_per_s", 0.1)))
        self.cycles_var = tk.StringVar(value=str(cfg.get("cycles", 1)))
        self.mass_var = tk.StringVar(value=str(cfg.get("mass_g", 1.0)))
        self.formula_var = tk.StringVar(value=cfg.get("formula", "LiFePO4"))
        self.electrons_var = tk.StringVar(value=str(cfg.get("electrons", 1)))
        self.efficiency_var = tk.StringVar(value=str(cfg.get("charge_efficiency", 1.0)))
        self.target_charge_display_var = tk.StringVar(value="─")
        self.target_charge_manual_var = tk.StringVar(value=str(cfg.get("target_charge_manual", 0)))
        self.stop_condition_var = tk.StringVar(value=cfg.get("stop_condition", StopCondition.CHARGE_COMPUTED.value))
        # Max duration の単位（s / min / h）
        self.max_duration_unit_var = tk.StringVar(value=cfg.get("max_duration_unit", "s"))

        # ウィジェット格納 dict  key -> [label_or_frame, entry_or_label]
        self._param_rows: dict[str, list[tk.Widget]] = {}

        # 行カウンタ（ミュータブルなリストで closure に渡す）
        r = [0]

        def entry(var: tk.StringVar) -> ttk.Entry:
            return ttk.Entry(g, textvariable=var, width=14)

        def add_row(key: str, label: str, widget: tk.Widget) -> None:
            lbl = ttk.Label(g, text=label)
            lbl.grid(row=r[0], column=0, sticky="w", padx=(2, 4), pady=1)
            widget.grid(row=r[0], column=1, sticky="ew", padx=2, pady=1)
            self._param_rows[key] = [lbl, widget]
            r[0] += 1

        # ── Mode selector（常に表示）──────────────────────────────────────────
        ttk.Label(g, text="Mode").grid(row=r[0], column=0, sticky="w", padx=(2, 4), pady=1)
        mode_cb = ttk.Combobox(
            g, textvariable=self.mode_var,
            values=[m.value for m in MeasurementMode], state="readonly", width=22)
        mode_cb.grid(row=r[0], column=1, sticky="ew", padx=2, pady=1)
        mode_cb.bind("<<ComboboxSelected>>", self.on_mode_change)
        r[0] += 1

        # ── CC 停止条件（CC モード専用）────────────────────────────────────────
        stop_frm = ttk.LabelFrame(g, text="Stop condition", padding=4)
        stop_frm.grid(row=r[0], column=0, columnspan=2, sticky="ew", padx=2, pady=2)
        self._param_rows["stop_condition"] = [stop_frm]
        for sc, label in [
            (StopCondition.TIME, "時間で停止"),
            (StopCondition.CHARGE_COMPUTED, "電気量で停止（質量・組成から計算）"),
            (StopCondition.CHARGE_MANUAL, "電気量で停止（手動入力）"),
        ]:
            ttk.Radiobutton(
                stop_frm, text=label,
                variable=self.stop_condition_var, value=sc.value,
                command=self.on_stop_condition_change,
            ).pack(anchor="w")
        r[0] += 1

        # ── 共通パラメータ行 ────────────────────────────────────────────
        add_row("sample_interval", "Sample interval (s)", entry(self.sample_interval_var))

        # Max duration → 入力欄 + 単位セレクタの複合ウィジェット行
        dur_frame = ttk.Frame(g)
        ttk.Entry(dur_frame, textvariable=self.max_duration_var, width=8).pack(side="left")
        ttk.Combobox(
            dur_frame, textvariable=self.max_duration_unit_var,
            values=["s", "min", "h"], state="readonly", width=5,
        ).pack(side="left", padx=(4, 0))
        add_row("max_duration", "Max duration", dur_frame)

        add_row("current",         "Current (mA)",        entry(self.current_var))
        add_row("voltage",         "Voltage (V)",         entry(self.voltage_var))
        add_row("current_limit",   "Current limit (mA)",  entry(self.current_limit_var))
        add_row("voltage_limit",   "Voltage limit (V)",   entry(self.voltage_limit_var))
        add_row("scan_start",      "CV start (V)",        entry(self.scan_start_var))
        add_row("scan_stop",       "CV stop (V)",         entry(self.scan_stop_var))
        add_row("scan_rate",       "CV rate (V/s)",       entry(self.scan_rate_var))
        add_row("cycles",          "CV cycles",           entry(self.cycles_var))

        # ── CC 電気量計算フィールド ─────────────────────────────────────────────
        add_row("mass",     "Mass (g)",        entry(self.mass_var))
        add_row("formula",  "Formula",         entry(self.formula_var))
        add_row("electrons", "Electrons (n)",  entry(self.electrons_var))
        add_row("efficiency", "Efficiency",    entry(self.efficiency_var))
        add_row("target_charge_display", "Target charge",
                ttk.Label(g, textvariable=self.target_charge_display_var, foreground="#2980b9"))

        # ── CC 手動入力 ─────────────────────────────────────────────────────────
        add_row("target_charge_manual", "Target charge (C)", entry(self.target_charge_manual_var))

        # 電気量を自動更新
        for var in (self.mass_var, self.formula_var, self.electrons_var, self.efficiency_var):
            var.trace_add("write", lambda *_: self._refresh_target_charge())

        # ── ボタン行 ───────────────────────────────────────────────────────────
        btn_row = ttk.Frame(g)
        btn_row.grid(row=r[0], column=0, columnspan=2, sticky="ew", pady=(8, 2))
        btn_row.columnconfigure((0, 1, 2), weight=1)
        ttk.Button(btn_row, text="▶ Start", command=self.start_measurement).grid(
            row=0, column=0, sticky="ew", padx=2)
        ttk.Button(btn_row, text="■ Stop",  command=self.stop_measurement).grid(
            row=0, column=1, sticky="ew", padx=2)
        self._calc_btn = ttk.Button(btn_row, text="クーロン計算...", command=self.open_coulomb_calculator)
        self._calc_btn.grid(row=0, column=2, sticky="ew", padx=2)

    # ── Status ─────────────────────────────────────────────────────────────────

    def _build_status_frame(self, parent: ttk.Frame) -> None:
        frm = ttk.LabelFrame(parent, text="Status", padding=6)
        frm.grid(row=2, column=0, sticky="ew")
        frm.columnconfigure(1, weight=1)

        self.message_var = tk.StringVar(value="Ready")
        self.voltage_status_var = tk.StringVar(value="─")
        self.current_status_var = tk.StringVar(value="─")
        self.charge_status_var = tk.StringVar(value="─")
        self.elapsed_status_var = tk.StringVar(value="─")

        for i, (label, var) in enumerate([
            ("Message", self.message_var),
            ("Voltage", self.voltage_status_var),
            ("Current", self.current_status_var),
            ("Charge",  self.charge_status_var),
            ("Elapsed", self.elapsed_status_var),
        ]):
            ttk.Label(frm, text=f"{label}:").grid(row=i, column=0, sticky="w")
            ttk.Label(frm, textvariable=var, foreground="#2980b9").grid(row=i, column=1, sticky="w")

        self._save_btn = ttk.Button(frm, text="💾 Save CSV...", command=self.save_csv, state="disabled")
        self._save_btn.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    # ── Plot ───────────────────────────────────────────────────────────────────

    def _build_plot_frame(self, parent: tk.Tk) -> None:
        frm = ttk.LabelFrame(parent, text="Live Plot", padding=8)
        frm.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.figure = Figure(figsize=(6, 5), dpi=100)
        self.axis = self.figure.add_subplot(111)
        self.axis.grid(True, alpha=0.3)
        self.canvas = FigureCanvasTkAgg(self.figure, master=frm)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.draw_idle()

    # ── Visibility logic ───────────────────────────────────────────────────────

    def _set_row_visible(self, key: str, visible: bool) -> None:
        for w in self._param_rows.get(key, []):
            if visible:
                w.grid()
            else:
                w.grid_remove()

    def on_mode_change(self, *_args) -> None:
        try:
            mode = MeasurementMode(self.mode_var.get())
        except ValueError:
            return

        visible = self._MODE_PARAMS.get(mode, set())
        all_general = {
            "sample_interval", "max_duration", "current", "voltage",
            "current_limit", "voltage_limit",
            "scan_start", "scan_stop", "scan_rate", "cycles",
        }
        for key in all_general:
            self._set_row_visible(key, key in visible)

        is_cc = (mode == MeasurementMode.CONSTANT_CURRENT)
        self._set_row_visible("stop_condition", is_cc)

        if is_cc:
            self._calc_btn.grid()
        else:
            self._calc_btn.grid_remove()

        # CC 専用フィールドは stop_condition に依存
        self.on_stop_condition_change()

    def on_stop_condition_change(self, *_args) -> None:
        try:
            mode = MeasurementMode(self.mode_var.get())
        except ValueError:
            return

        if mode != MeasurementMode.CONSTANT_CURRENT:
            for key in ("mass", "formula", "electrons", "efficiency",
                        "target_charge_display", "target_charge_manual"):
                self._set_row_visible(key, False)
            return

        sc = StopCondition(self.stop_condition_var.get())
        computed = (sc == StopCondition.CHARGE_COMPUTED)
        manual = (sc == StopCondition.CHARGE_MANUAL)

        for key in ("mass", "formula", "electrons", "efficiency", "target_charge_display"):
            self._set_row_visible(key, computed)
        self._set_row_visible("target_charge_manual", manual)

    # ── Business logic ─────────────────────────────────────────────────────────

    def connect_device(self) -> None:
        device_config = self.config.setdefault("device", {})
        device_config["mode"] = "simulation" if self.simulation_var.get() else "gpib"
        device_config["resource_name"] = self.resource_var.get().strip()
        self.controller = ElectrochemistryController(build_device(device_config))
        try:
            state = self.controller.connect(device_config["resource_name"])
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
            self.target_charge_display_var.set(format_charge(params.compute_target_charge()))
        except Exception as exc:
            self.target_charge_display_var.set(str(exc))

    def build_parameters(self) -> MeasurementParameters:
        mode = MeasurementMode(self.mode_var.get())
        sc = StopCondition(self.stop_condition_var.get())
        stop_on_charge = (mode == MeasurementMode.CONSTANT_CURRENT and sc != StopCondition.TIME)

        params = MeasurementParameters(
            mode=mode,
            sample_interval_s=float(self.sample_interval_var.get()),
            max_duration_s=self._max_duration_s(),    # 単位変換して秒に
            current_a=float(self.current_var.get()) / 1000,       # mA → A
            voltage_v=float(self.voltage_var.get()),
            current_limit_a=float(self.current_limit_var.get()) / 1000,  # mA → A
            voltage_limit_v=float(self.voltage_limit_var.get()),
            scan_start_v=float(self.scan_start_var.get()),
            scan_stop_v=float(self.scan_stop_var.get()),
            scan_rate_v_per_s=float(self.scan_rate_var.get()),
            cycles=int(float(self.cycles_var.get())),
            mass_g=float(self.mass_var.get()),
            formula=self.formula_var.get(),
            electrons=int(float(self.electrons_var.get())),
            charge_efficiency=float(self.efficiency_var.get()),
            stop_on_charge=stop_on_charge,
        )

        if mode == MeasurementMode.CONSTANT_CURRENT:
            if sc == StopCondition.CHARGE_COMPUTED:
                params.compute_target_charge()
            elif sc == StopCondition.CHARGE_MANUAL:
                params.target_charge_c = float(self.target_charge_manual_var.get())
            # TIME の場合は stop_on_charge=False なので target_charge_c 無視

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
            self._save_btn.config(state="disabled")
            self.manager.start(params)
            self.message_var.set("Measurement started")
        except Exception as exc:
            messagebox.showerror("測定エラー", str(exc))

    def stop_measurement(self) -> None:
        if self.manager is not None:
            self.manager.stop()

    # ── CSV save ───────────────────────────────────────────────────────────────

    def _max_duration_s(self) -> float:
        """入力値と単位セレクタから Max duration (秒) を返す。"""
        val = float(self.max_duration_var.get())
        factor = {"s": 1.0, "min": 60.0, "h": 3600.0}.get(self.max_duration_unit_var.get(), 1.0)
        return val * factor

    def _build_csv_metadata(self) -> dict:
        """測定条件のメタデータ辞書を構築する（CSV ヘッダ用）。"""
        mode = self.mode_var.get()
        meta: dict = {
            "Mode": mode,
            "Sample interval": f"{self.sample_interval_var.get()} s",
            "Max duration": (
                f"{self.max_duration_var.get()} {self.max_duration_unit_var.get()}"
                f" ({self._max_duration_s():.1f} s)"
            ),
        }
        if mode == MeasurementMode.CONSTANT_CURRENT.value:
            meta["Current"] = f"{self.current_var.get()} mA"
            meta["Current limit"] = f"{self.current_limit_var.get()} mA"
            meta["Voltage limit"] = f"{self.voltage_limit_var.get()} V"
            meta["Stop condition"] = self.stop_condition_var.get()
            sc = StopCondition(self.stop_condition_var.get())
            if sc == StopCondition.CHARGE_COMPUTED:
                meta["Formula"] = self.formula_var.get()
                meta["Mass"] = f"{self.mass_var.get()} g"
                meta["Electrons"] = self.electrons_var.get()
                meta["Efficiency"] = self.efficiency_var.get()
                meta["Target charge"] = self.target_charge_display_var.get()
            elif sc == StopCondition.CHARGE_MANUAL:
                meta["Target charge (manual)"] = f"{self.target_charge_manual_var.get()} C"
        elif mode == MeasurementMode.CONSTANT_VOLTAGE.value:
            meta["Voltage"] = f"{self.voltage_var.get()} V"
            meta["Current limit"] = f"{self.current_limit_var.get()} mA"
            meta["Voltage limit"] = f"{self.voltage_limit_var.get()} V"
        elif mode == MeasurementMode.CV.value:
            meta["CV start"] = f"{self.scan_start_var.get()} V"
            meta["CV stop"] = f"{self.scan_stop_var.get()} V"
            meta["CV rate"] = f"{self.scan_rate_var.get()} V/s"
            meta["CV cycles"] = self.cycles_var.get()
            meta["Current limit"] = f"{self.current_limit_var.get()} mA"
            meta["Voltage limit"] = f"{self.voltage_limit_var.get()} V"
        return meta

    def save_csv(self) -> None:
        if self.manager is None or not self.manager.result.time_s:
            messagebox.showinfo("保存", "保存するデータがありません")
            return
        path_str = filedialog.asksaveasfilename(
            title="データを CSV で保存",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path_str:
            return
        try:
            save_measurement_csv(
                Path(path_str), self.manager.result, metadata=self._build_csv_metadata()
            )
            messagebox.showinfo("保存完了", f"保存しました:\n{path_str}")
        except Exception as exc:
            messagebox.showerror("保存エラー", str(exc))

    # ── Coulomb calculator sub-window ──────────────────────────────────────────

    def open_coulomb_calculator(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("クーロン計算")
        win.geometry("360x330")
        win.resizable(False, False)
        win.grab_set()  # モーダル

        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        cv_mass     = tk.StringVar(value=self.mass_var.get())
        cv_formula  = tk.StringVar(value=self.formula_var.get())
        cv_electrons = tk.StringVar(value=self.electrons_var.get())
        cv_eff      = tk.StringVar(value=self.efficiency_var.get())
        cv_current  = tk.StringVar(value=self.current_var.get())  # mA
        res_charge  = tk.StringVar(value="─")
        res_time    = tk.StringVar(value="─")

        def recalc(*_):
            try:
                q = charge_from_mass_formula(
                    float(cv_mass.get()), cv_formula.get(),
                    int(float(cv_electrons.get())), float(cv_eff.get()),
                )
                res_charge.set(format_charge(q))
                i_a = float(cv_current.get()) / 1000
                if i_a > 0:
                    t_s = q / i_a
                    if t_s < 60:
                        res_time.set(f"{t_s:.1f} s")
                    elif t_s < 3600:
                        res_time.set(f"{t_s / 60:.1f} min")
                    else:
                        res_time.set(f"{t_s / 3600:.2f} h")
                else:
                    res_time.set("─")
            except Exception as exc:
                res_charge.set(str(exc))
                res_time.set("─")

        def apply_to_main():
            self.mass_var.set(cv_mass.get())
            self.formula_var.set(cv_formula.get())
            self.electrons_var.set(cv_electrons.get())
            self.efficiency_var.set(cv_eff.get())
            self.current_var.set(cv_current.get())
            win.destroy()

        fields = [
            ("Mass (g)",       cv_mass),
            ("Formula",        cv_formula),
            ("Electrons (n)",  cv_electrons),
            ("Efficiency",     cv_eff),
            ("Current (mA)",   cv_current),
        ]
        for i, (lbl, var) in enumerate(fields):
            ttk.Label(frm, text=lbl).grid(row=i, column=0, sticky="w", pady=2, padx=(0, 6))
            e = ttk.Entry(frm, textvariable=var, width=18)
            e.grid(row=i, column=1, sticky="ew", pady=2)
            var.trace_add("write", recalc)

        n = len(fields)
        ttk.Separator(frm, orient="horizontal").grid(
            row=n, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(frm, text="Required charge").grid(row=n+1, column=0, sticky="w")
        ttk.Label(frm, textvariable=res_charge, foreground="#2980b9").grid(row=n+1, column=1, sticky="w")
        ttk.Label(frm, text="Est. time").grid(row=n+2, column=0, sticky="w")
        ttk.Label(frm, textvariable=res_time, foreground="#2980b9").grid(row=n+2, column=1, sticky="w")

        bf = ttk.Frame(frm)
        bf.grid(row=n+3, column=0, columnspan=2, pady=10, sticky="ew")
        bf.columnconfigure((0, 1), weight=1)
        ttk.Button(bf, text="メインに適用", command=apply_to_main).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(bf, text="閉じる",       command=win.destroy).grid(row=0, column=1, sticky="ew", padx=2)

        recalc()

    # ── Event polling & plot ───────────────────────────────────────────────────

    # 1サイクルで描画する最大データ点数（これを超えた分は間引きダウンサンプリング）
    _MAX_PLOT_POINTS: int = 2000
    # プロット更新の最小間隔（秒）：これより短い間隔では描画しない
    _PLOT_INTERVAL_S: float = 1.0

    def _poll_events(self) -> None:
        if self.manager is not None:
            latest_point = None
            while True:
                try:
                    event = self.manager.events.get_nowait()
                except Exception:
                    break
                if event.kind == "point":
                    # ステータス表示は最新点だけ更新（中間点はスキップ）
                    latest_point = event.payload["point"]
                else:
                    # "finished" / "error" / "status" は必ず処理
                    self._handle_nonepoint_event(event.kind, event.payload)

            if latest_point is not None:
                self.voltage_status_var.set(format_voltage(latest_point.voltage_v))
                self.current_status_var.set(format_current(latest_point.current_a))
                self.charge_status_var.set(format_charge(latest_point.charge_c))
                self.elapsed_status_var.set(f"{latest_point.time_s:.1f} s")

                # プロットは _PLOT_INTERVAL_S 秒に１回だけ更新
                now = time.monotonic()
                if now - getattr(self, "_last_plot_time", 0.0) >= self._PLOT_INTERVAL_S:
                    self._update_plot()
                    self._last_plot_time = now

        self.root.after(100, self._poll_events)

    def _handle_nonepoint_event(self, kind: str, payload: dict) -> None:
        """"point" 以外のイベントを処理する。"""
        if kind == "status":
            self.message_var.set(payload.get("message", ""))
        elif kind == "finished":
            self.message_var.set(f"Finished: {payload.get('reason', '')}")
            self._update_plot()             # 終了時は必ず最終プロットを描画
            self._save_btn.config(state="normal")   # CSV 保存ボタン有効化
        elif kind == "error":
            msg = payload.get("message", "Unknown error")
            self.message_var.set(msg)
            self._update_plot()
            self._save_btn.config(state="normal")
            messagebox.showerror("測定エラー", msg)

    def _ensure_plot_line(self, mode: str) -> None:
        """モードに対応した Line2D オブジェクトを初期化する。
        同じモードなら再利用。変わったときだけ axis.clear() を実行。
        """
        if getattr(self, "_plot_mode", None) == mode:
            return  # 既存の Line2D を再利用→ set_data() だけで済む

        self.axis.clear()
        self.axis.grid(True, alpha=0.3)
        if mode == MeasurementMode.CV.value:
            self.axis.set_xlabel("Voltage (V)")
            self.axis.set_ylabel("Current (A)")
            (self._plot_line,) = self.axis.plot([], [], color="#c0392b", linewidth=1.0)
        elif mode == MeasurementMode.CONSTANT_VOLTAGE.value:
            self.axis.set_xlabel("Time (s)")
            self.axis.set_ylabel("Current (A)")
            (self._plot_line,) = self.axis.plot([], [], color="#2980b9", linewidth=1.0)
        else:
            self.axis.set_xlabel("Time (s)")
            self.axis.set_ylabel("Voltage (V)")
            (self._plot_line,) = self.axis.plot([], [], color="#16a085", linewidth=1.0)
        self._plot_mode = mode

    def _update_plot(self) -> None:
        if self.manager is None:
            return
        # snapshot() で 4 リストを同じ長さで揃えてから読む（race condition 対策）
        result = self.manager.result.snapshot()
        n = len(result.time_s)
        if n == 0:
            return
        mode = result.mode

        # ダウンサンプリング：描画点数を _MAX_PLOT_POINTS 以内に押さえる
        step = max(1, n // self._MAX_PLOT_POINTS)
        t  = result.time_s[::step]
        v  = result.voltage_v[::step]
        ia = result.current_a[::step]

        # モード変更時のみ clear() する（毎回 clear()+plot() しない）
        self._ensure_plot_line(mode)

        if mode == MeasurementMode.CV.value:
            self._plot_line.set_data(v, ia)
        elif mode == MeasurementMode.CONSTANT_VOLTAGE.value:
            self._plot_line.set_data(t, ia)
        else:
            self._plot_line.set_data(t, v)

        self.axis.relim()
        self.axis.autoscale_view()
        self.canvas.draw_idle()

    def _save_params_to_config(self) -> None:
        """GUIの全入力値を config 辞書に書き戻す（次回起動時の初期値引き継ぎ）。"""
        cfg = self.config.setdefault("measurement", {})
        try:
            cfg["mode"]              = self.mode_var.get()
            cfg["sample_interval_s"] = float(self.sample_interval_var.get())
            cfg["max_duration_s"]    = float(self.max_duration_var.get())
            cfg["current_a"]         = float(self.current_var.get()) / 1000      # mA → A
            cfg["voltage_v"]         = float(self.voltage_var.get())
            cfg["current_limit_a"]   = float(self.current_limit_var.get()) / 1000  # mA → A
            cfg["voltage_limit_v"]   = float(self.voltage_limit_var.get())
            cfg["scan_start_v"]      = float(self.scan_start_var.get())
            cfg["scan_stop_v"]       = float(self.scan_stop_var.get())
            cfg["scan_rate_v_per_s"] = float(self.scan_rate_var.get())
            cfg["cycles"]            = int(float(self.cycles_var.get()))
            cfg["mass_g"]            = float(self.mass_var.get())
            cfg["formula"]           = self.formula_var.get()
            cfg["electrons"]         = int(float(self.electrons_var.get()))
            cfg["charge_efficiency"] = float(self.efficiency_var.get())
            cfg["stop_condition"]       = self.stop_condition_var.get()
            cfg["target_charge_manual"]  = float(self.target_charge_manual_var.get())
            cfg["max_duration_unit"]     = self.max_duration_unit_var.get()
        except (ValueError, tk.TclError):
            pass  # 入力値の変換失敗は無視

    def close(self) -> None:
        try:
            self.disconnect_device()
            self._save_params_to_config()  # 入力値を保存
            save_json(self.config_path, self.config)
        finally:
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()