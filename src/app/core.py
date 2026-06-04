from __future__ import annotations

import math
import queue
import random
import re
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

FARADAY_CONSTANT = 96485.33212

try:
    from rdkit import Chem
    PT = Chem.GetPeriodicTable()
except Exception as exc:  # pragma: no cover - RDKit must be installed
    raise RuntimeError("RDKit が見つかりません。RDKit をインストールしてください。Windows の場合は対応する wheel を用意してください") from exc


def _atomic_weight(symbol: str) -> float:
    z = PT.GetAtomicNumber(symbol)
    if not z:
        raise ValueError(f"不明な元素: {symbol}")
    return float(PT.GetAtomicWeight(z))


class MeasurementMode(str, Enum):
    CONSTANT_CURRENT = "constant_current"
    CONSTANT_VOLTAGE = "constant_voltage"
    CV = "cv"


@dataclass(slots=True)
class MeasurementParameters:
    mode: MeasurementMode = MeasurementMode.CONSTANT_CURRENT
    sample_interval_s: float = 1.0
    max_duration_s: float = 3600.0
    current_a: float = 0.01
    voltage_v: float = 1.0
    current_limit_a: float = 1.0
    voltage_limit_v: float = 10.0
    scan_start_v: float = -1.0
    scan_stop_v: float = 1.0
    scan_rate_v_per_s: float = 0.1
    cycles: int = 1
    mass_g: float = 1.0
    formula: str = "LiFePO4"
    electrons: int = 1
    charge_efficiency: float = 1.0
    target_charge_c: float = 0.0
    # stop_on_charge=True のとき CC モードで target_charge_c に達したら自動停止する。
    # False にすると max_duration_s のみで停止する（時間停止モード）。
    stop_on_charge: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "MeasurementParameters":
        mode = MeasurementMode(data.get("mode", "constant_current"))
        return cls(
            mode=mode,
            sample_interval_s=float(data.get("sample_interval_s", 1.0)),
            max_duration_s=float(data.get("max_duration_s", 3600.0)),
            current_a=float(data.get("current_a", 0.01)),
            voltage_v=float(data.get("voltage_v", 1.0)),
            current_limit_a=float(data.get("current_limit_a", 1.0)),
            voltage_limit_v=float(data.get("voltage_limit_v", 10.0)),
            scan_start_v=float(data.get("scan_start_v", -1.0)),
            scan_stop_v=float(data.get("scan_stop_v", 1.0)),
            scan_rate_v_per_s=float(data.get("scan_rate_v_per_s", 0.1)),
            cycles=int(data.get("cycles", 1)),
            mass_g=float(data.get("mass_g", 1.0)),
            formula=str(data.get("formula", "LiFePO4")),
            electrons=int(data.get("electrons", 1)),
            charge_efficiency=float(data.get("charge_efficiency", 1.0)),
            stop_on_charge=bool(data.get("stop_on_charge", True)),
        )

    def compute_target_charge(self) -> float:
        self.target_charge_c = charge_from_mass_formula(
            mass_g=self.mass_g,
            formula=self.formula,
            electrons=self.electrons,
            charge_efficiency=self.charge_efficiency,
        )
        return self.target_charge_c


@dataclass(slots=True)
class MeasurementPoint:
    time_s: float
    voltage_v: float
    current_a: float
    charge_c: float


@dataclass(slots=True)
class MeasurementResult:
    time_s: list[float] = field(default_factory=list)
    voltage_v: list[float] = field(default_factory=list)
    current_a: list[float] = field(default_factory=list)
    charge_c: list[float] = field(default_factory=list)
    mode: str = ""
    finished_reason: str = ""

    def append(self, point: MeasurementPoint) -> None:
        self.time_s.append(point.time_s)
        self.voltage_v.append(point.voltage_v)
        self.current_a.append(point.current_a)
        self.charge_c.append(point.charge_c)

    def safe_n(self) -> int:
        """4リストの最小長を返す（GUI スレッドがスレッドセーフに使える点数）。

        Python の GIL 下では len() はアトミックなので、
        この値以内で各リストにアクセスすれば範囲外エラーは起きない。
        全データをコピーしないため、何時間動かしてもメモリを圧迫しない。
        """
        return min(len(self.time_s), len(self.voltage_v),
                   len(self.current_a), len(self.charge_c))

    def snapshot(self) -> "MeasurementResult":
        """GUIスレッドが安全に読めるスナップショットを返す。

        4つのリストを同じ長さで切り詰めて返す。
        Python の GIL の下でリストの len()・slice はアトミックなので
        このアプローチで競合状態を安全に回避できる。
        """
        n = self.safe_n()
        snap = MeasurementResult(mode=self.mode, finished_reason=self.finished_reason)
        snap.time_s   = self.time_s[:n]
        snap.voltage_v = self.voltage_v[:n]
        snap.current_a = self.current_a[:n]
        snap.charge_c  = self.charge_c[:n]
        return snap


@dataclass(slots=True)
class DeviceState:
    connected: bool = False
    resource_name: str = ""
    idn: str = ""
    mode: str = "idle"
    voltage_v: float = 0.0
    current_a: float = 0.0
    output_enabled: bool = False


def _tokenize(formula: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(formula):
        char = formula[index]
        if char.isspace():
            index += 1
            continue
        if char in "()[]{}":
            tokens.append(char)
            index += 1
            continue
        if char.isdigit():
            end = index + 1
            while end < len(formula) and formula[end].isdigit():
                end += 1
            tokens.append(formula[index:end])
            index = end
            continue
        if char.isalpha():
            end = index + 1
            while end < len(formula) and formula[end].islower():
                end += 1
            tokens.append(formula[index:end])
            index = end
            continue
        raise ValueError(f"Unsupported character in formula: {char}")
    return tokens


def _parse_tokens(tokens: list[str], start: int = 0) -> tuple[dict[str, int], int]:
    counts: defaultdict[str, int] = defaultdict(int)
    index = start
    while index < len(tokens):
        token = tokens[index]
        if token in ")]}":
            return dict(counts), index + 1
        if token in "([{":
            nested, index = _parse_tokens(tokens, index + 1)
            multiplier = 1
            if index < len(tokens) and tokens[index].isdigit():
                multiplier = int(tokens[index])
                index += 1
            for element, count in nested.items():
                counts[element] += count * multiplier
            continue
        if token.isdigit():
            raise ValueError("Unexpected number in formula")
        element = token
        try:
            _atomic_weight(element)
        except ValueError:
            raise ValueError(f"Unsupported element: {element}")
        amount = 1
        if index + 1 < len(tokens) and tokens[index + 1].isdigit():
            amount = int(tokens[index + 1])
            index += 1
        counts[element] += amount
        index += 1
    return dict(counts), index


def molar_mass(formula: str) -> float:
    tokens = _tokenize(formula)
    counts, index = _parse_tokens(tokens)
    if index != len(tokens):
        raise ValueError("Failed to parse full formula")
    mass = 0.0
    for element, amount in counts.items():
        mass += _atomic_weight(element) * amount
    return mass


def amount_of_substance(mass_g: float, formula: str) -> float:
    return mass_g / molar_mass(formula)


def charge_from_mass_formula(mass_g: float, formula: str, electrons: int, charge_efficiency: float = 1.0) -> float:
    return amount_of_substance(mass_g, formula) * electrons * FARADAY_CONSTANT * charge_efficiency


def format_current(value_a: float) -> str:
    abs_value = abs(value_a)
    if abs_value >= 1:
        return f"{value_a:.6f} A"
    if abs_value >= 1e-3:
        return f"{value_a * 1e3:.3f} mA"
    if abs_value >= 1e-6:
        return f"{value_a * 1e6:.3f} uA"
    return f"{value_a * 1e9:.3f} nA"


def format_voltage(value_v: float) -> str:
    return f"{value_v:.6f} V"


def format_charge(value_c: float) -> str:
    abs_value = abs(value_c)
    if abs_value >= 1:
        return f"{value_c:.6f} C"
    if abs_value >= 1e-3:
        return f"{value_c * 1e3:.3f} mC"
    return f"{value_c * 1e6:.3f} uC"


def safe_resource_name(resource_name: str, gpib_address: str) -> str:
    return resource_name.strip() or (f"GPIB0::{gpib_address.strip()}::INSTR" if gpib_address.strip() else "")


class BaseDevice(ABC):
    @abstractmethod
    def connect(self, resource_name: str) -> DeviceState:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def identify(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def set_constant_current(self, current_a: float, voltage_limit_v: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_constant_voltage(self, voltage_v: float, current_limit_a: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_voltage(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def read_current(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def output(self, enabled: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_output_voltage(self, voltage_v: float) -> None:
        """出力中に電位値だけを更新する（モード初期化コマンドは送らない）。"""
        raise NotImplementedError

    @abstractmethod
    def update_output_current(self, current_a: float) -> None:
        """出力中に電流値だけを更新する（モード初期化コマンドは送らない）。"""
        raise NotImplementedError

    @abstractmethod
    def write_raw_command(self, cmd: str) -> None:
        """デバイスに直接コマンドを書き込む。"""
        raise NotImplementedError


try:
    import pyvisa
except Exception:  # pragma: no cover
    pyvisa = None


@dataclass(slots=True)
class R6244Commands:
    device_clear: str = "C"
    dc_operation: str = "MD0"
    constant_voltage_mode: str = "VF"
    constant_current_mode: str = "IF"
    operate: str = "E"
    hold: str = "H"
    measure_current: str = "F2"
    measure_voltage: str = "F1"
    # 測定レンジコマンド（空文字列 = 送信しない / デバイスデフォルト使用）
    # CV ・定電位模式では電流測定レンジを適切に設定することで量子化を解消できる。
    # R6244 のコマンド例: 電流レンジ → “IRN 2”, 電位レンジ → “VRN 1”
    current_range_cmd: str = ""
    voltage_range_cmd: str = ""


@dataclass(slots=True)
class R6244Device(BaseDevice):
    commands: R6244Commands = field(default_factory=R6244Commands)
    timeout_ms: int = 5000

    def __post_init__(self) -> None:
        self._resource = None
        self._rm = None
        self._state = DeviceState()
        self.debug_mode = False  # Enable to see sent commands

    @property
    def state(self) -> DeviceState:
        return self._state

    def connect(self, resource_name: str) -> DeviceState:
        if pyvisa is None:
            raise RuntimeError("pyvisa が利用できません。オフライン依存を導入してください。")
        self._rm = pyvisa.ResourceManager()
        self._resource = self._rm.open_resource(resource_name)
        self._resource.timeout = self.timeout_ms
        self._write(self.commands.device_clear)
        self._state = DeviceState(True, resource_name, "R6244 Device", "idle", 0.0, 0.0, False)
        return self._state

    def disconnect(self) -> None:
        try:
            self.output(False)
        except Exception:
            pass
        try:
            if self._resource is not None:
                self._resource.close()
        finally:
            if self._rm is not None:
                self._rm.close()
            self._resource = None
            self._rm = None
            self._state = DeviceState()

    def identify(self) -> str:
        if self._resource is None:
            return "SIMULATED"
        return "R6244 Device"

    def _log_gpib(self, direction: str, text: str) -> None:
        from datetime import datetime
        import pathlib
        try:
            log_dir = pathlib.Path(__file__).resolve().parent.parent.parent
            log_path = log_dir / "gpib_communication.log"
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} {direction} {repr(text)}\n")
        except Exception as e:
            print(f"[LOG ERROR] {e}")

    def _write(self, text: str) -> None:
        self._log_gpib("[SEND]", text)
        if self.debug_mode:
            print(f"[SEND] {repr(text)}")
        if self._resource is not None:
            self._resource.write(text)

    def _query(self, text: str) -> str:
        self._log_gpib("[QUERY]", text)
        if self.debug_mode:
            print(f"[QUERY] {repr(text)}")
        if self._resource is None:
            return ""
        response = str(self._resource.query(text)).strip()
        self._log_gpib("[RESP]", response)
        if self.debug_mode:
            print(f"[RESP] {repr(response)}")
        return response

    def set_constant_current(self, current_a: float, voltage_limit_v: float) -> None:
        self._state.mode = "constant_current"
        self._state.current_a = current_a
        self._write(self.commands.dc_operation)
        self._write(self.commands.constant_current_mode)
        
        # Send voltage compliance limit (using compatibility syntax)
        self._write(f"D {voltage_limit_v}V")

        # Current range configuration
        if self.commands.current_range_cmd:
            cmd_str = self.commands.current_range_cmd.strip().upper()
            if cmd_str == "AUTO":
                self._write("F2")
                self._write("R0")
            elif cmd_str:
                self._write("F2")
                self._write(cmd_str)

        # Voltage range configuration
        if self.commands.voltage_range_cmd:
            cmd_str = self.commands.voltage_range_cmd.strip().upper()
            if cmd_str == "AUTO":
                self._write("F1")
                self._write("R0")
            elif cmd_str:
                self._write("F1")
                self._write(cmd_str)

        # R6244 電流コマンドは UA（マイクロアンペア）単位。
        # VBA: DCI = Int(DCI_ua * 100) / 100  → 0.01 µA 精度に切り捨て
        # VBA: Str() は正の数に先頭スペースを付けるが、整数は小数点なし。
        current_ua = current_a * 1e6
        current_ua_truncated = int(current_ua * 100) / 100
        if current_ua_truncated == int(current_ua_truncated):
            num_str = str(int(current_ua_truncated))  # 例: "10000"（小数点なし）
        else:
            num_str = str(current_ua_truncated)       # 例: "10000.5"
        cmd = f"D {num_str}UA"  # 先頭スペース = VBA Str() の正数フォーマット
        self._write(cmd)

    def set_constant_voltage(self, voltage_v: float, current_limit_a: float) -> None:
        self._state.mode = "constant_voltage"
        self._state.voltage_v = voltage_v
        self._write(self.commands.dc_operation)
        self._write(self.commands.constant_voltage_mode)

        # Send current compliance limit (using compatibility syntax)
        self._write(f"D {current_limit_a}A")

        # Current range configuration
        if self.commands.current_range_cmd:
            cmd_str = self.commands.current_range_cmd.strip().upper()
            if cmd_str == "AUTO":
                self._write("F2")
                self._write("R0")
            elif cmd_str:
                self._write("F2")
                self._write(cmd_str)

        # Voltage range configuration
        if self.commands.voltage_range_cmd:
            cmd_str = self.commands.voltage_range_cmd.strip().upper()
            if cmd_str == "AUTO":
                self._write("F1")
                self._write("R0")
            elif cmd_str:
                self._write("F1")
                self._write(cmd_str)

        # VBA Str() emulation: prepend space before number
        cmd = f"D {voltage_v}V"
        self._write(cmd)

    # R6244 応答から数値を抽出する共通関数。
    # VBA: Mid(response, 4, 11) → 3文字ヘッダの後に数値。
    # 後第に複数フォーマット（円笠数記法・固定小数点）に対応するため正規表現で。
    _RESPONSE_NUM_RE = re.compile(
        r'[+-]?\d+\.?\d*(?:[Ee][+-]?\d+)?'
    )

    def _parse_response_value(self, response: str) -> float | None:
        """応答文字列から最初の数値を返す。

        VBA: Val(Mid(response, 4, 11))
        実機の応答フォーマットが少しずれていても確実に取り出せるようヘッダ(3文字)以降を対象とする。"""
        if self.debug_mode:
            print(f"[PARSE] response={repr(response)}")
        # ヘッダ 3 文字をスキップして数値を検索
        search_str = response[3:] if len(response) > 3 else response
        m = self._RESPONSE_NUM_RE.search(search_str)
        if m is None:
            if self.debug_mode:
                print(f"[PARSE] 数値が見つかりませんでした")
            return None
        try:
            return float(m.group())
        except ValueError:
            return None

    def read_voltage(self) -> float:
        response = self._query(self.commands.measure_voltage)
        value = self._parse_response_value(response)
        if value is not None:
            if abs(value) <= 25.0:
                self._state.voltage_v = value
            else:
                print(f"[WARNING] 無効な電圧測定値を無視しました: {value}")
        return self._state.voltage_v

    def read_current(self) -> float:
        response = self._query(self.commands.measure_current)
        value = self._parse_response_value(response)
        if value is not None:
            if abs(value) <= 12.0:
                self._state.current_a = value
            else:
                print(f"[WARNING] 無効な電流測定値を無視しました: {value}")
        return self._state.current_a

    def output(self, enabled: bool) -> None:
        self._state.output_enabled = enabled
        self._write(self.commands.operate if enabled else self.commands.hold)

    def update_output_voltage(self, voltage_v: float) -> None:
        """出力中に電位値だけを更新する（MD0・VF は送らない）。"""
        self._state.voltage_v = voltage_v
        cmd = f"D {voltage_v}V"
        self._write(cmd)

    def update_output_current(self, current_a: float) -> None:
        """出力中に電流値だけを更新する（MD0・IF は送らない）。"""
        self._state.current_a = current_a
        current_ua = current_a * 1e6
        current_ua_truncated = int(current_ua * 100) / 100
        if current_ua_truncated == int(current_ua_truncated):
            num_str = str(int(current_ua_truncated))
        else:
            num_str = str(current_ua_truncated)
        cmd = f"D {num_str}UA"
        self._write(cmd)

    def write_raw_command(self, cmd: str) -> None:
        if cmd:
            self._write(cmd)


@dataclass(slots=True)
class SimulatedR6244Device(BaseDevice):
    resource_name: str = "SIMULATOR"
    resistance_ohm: float = 10.0

    def __post_init__(self) -> None:
        self._state = DeviceState(False, self.resource_name, "SIMULATED R6244", "idle", 0.0, 0.0, False)
        self.target_current_a = 0.0
        self.target_voltage_v = 0.0

    @property
    def state(self) -> DeviceState:
        return self._state

    def connect(self, resource_name: str) -> DeviceState:
        self._state = DeviceState(True, resource_name, "SIMULATED R6244", "idle", 0.0, 0.0, False)
        return self._state

    def disconnect(self) -> None:
        self._state = DeviceState(False, self.resource_name, "SIMULATED R6244", "idle", 0.0, 0.0, False)

    def identify(self) -> str:
        return "SIMULATED R6244"

    def set_constant_current(self, current_a: float, voltage_limit_v: float) -> None:
        self._state.mode = "constant_current"
        self.target_current_a = current_a

    def set_constant_voltage(self, voltage_v: float, current_limit_a: float) -> None:
        self._state.mode = "constant_voltage"
        self.target_voltage_v = voltage_v

    def read_voltage(self) -> float:
        if self._state.output_enabled:
            self._state.voltage_v += (self.target_voltage_v - self._state.voltage_v) * 0.2
        self._state.voltage_v += random.uniform(-0.005, 0.005)
        return self._state.voltage_v

    def read_current(self) -> float:
        if self._state.output_enabled:
            self._state.current_a += (self.target_current_a - self._state.current_a) * 0.2
            if self._state.mode == "constant_voltage":
                self._state.current_a = self._state.voltage_v / self.resistance_ohm
        self._state.current_a += random.uniform(-0.0005, 0.0005)
        return self._state.current_a

    def output(self, enabled: bool) -> None:
        self._state.output_enabled = enabled

    def update_output_voltage(self, voltage_v: float) -> None:
        self._state.voltage_v = voltage_v
        self.target_voltage_v = voltage_v

    def update_output_current(self, current_a: float) -> None:
        self._state.current_a = current_a
        self.target_current_a = current_a

    def write_raw_command(self, cmd: str) -> None:
        pass


def build_device(device_config: dict) -> BaseDevice:
    mode = device_config.get("mode", "simulation")
    if mode == "simulation":
        return SimulatedR6244Device(resource_name=device_config.get("resource_name", "SIMULATOR"))
    commands = R6244Commands(**device_config.get("commands", {}))
    return R6244Device(commands=commands, timeout_ms=int(device_config.get("timeout_ms", 5000)))


@dataclass(slots=True)
class ElectrochemistryController:
    device: BaseDevice

    def connect(self, resource_name: str) -> DeviceState:
        return self.device.connect(resource_name)

    def disconnect(self) -> None:
        self.device.disconnect()

    def identify(self) -> str:
        return self.device.identify()

    def set_constant_current(self, current_a: float, voltage_limit_v: float) -> None:
        self.device.set_constant_current(current_a, voltage_limit_v)

    def set_constant_voltage(self, voltage_v: float, current_limit_a: float) -> None:
        self.device.set_constant_voltage(voltage_v, current_limit_a)

    def read_voltage(self) -> float:
        return self.device.read_voltage()

    def read_current(self) -> float:
        return self.device.read_current()

    def output(self, enabled: bool) -> None:
        self.device.output(enabled)

    def update_output_voltage(self, voltage_v: float) -> None:
        self.device.update_output_voltage(voltage_v)

    def update_output_current(self, current_a: float) -> None:
        self.device.update_output_current(current_a)

    def write_raw_command(self, cmd: str) -> None:
        self.device.write_raw_command(cmd)


def within_limits(voltage_v: float, current_a: float, voltage_limit_v: float, current_limit_a: float) -> bool:
    return abs(voltage_v) <= abs(voltage_limit_v) and abs(current_a) <= abs(current_limit_a)


@dataclass(slots=True)
class MeasurementEvent:
    kind: str
    payload: dict


class MeasurementManager:
    def __init__(self, controller: ElectrochemistryController) -> None:
        self.controller = controller
        self.events: "queue.Queue[MeasurementEvent]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.result = MeasurementResult()

    def start(self, params: MeasurementParameters) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("測定中です")
        self._stop_event.clear()
        self.result = MeasurementResult(mode=params.mode.value)
        self._thread = threading.Thread(target=self._run, args=(params,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        # VISA機器への HOLD コマンドは測定スレッドの finally ブロックで送信する。
        # ここで呼び出すと GUI スレッドから VISA を抓り、タイムアウトの原因になる。
        self.events.put(MeasurementEvent("status", {"message": "停止要求を送信しました"}))

    def _emit(self, kind: str, **payload: object) -> None:
        self.events.put(MeasurementEvent(kind, payload))

    def _run(self, params: MeasurementParameters) -> None:
        start_time = time.monotonic()
        accumulated_charge = 0.0
        out_of_limit_count = 0
        try:
            if params.mode == MeasurementMode.CONSTANT_CURRENT:
                # stop_on_charge=True の場合のみ電気量から目標値を計算する
                if params.stop_on_charge and params.target_charge_c <= 0:
                    params.compute_target_charge()
                self.controller.set_constant_current(params.current_a, params.voltage_limit_v)
            elif params.mode == MeasurementMode.CONSTANT_VOLTAGE:
                if params.stop_on_charge and params.target_charge_c <= 0:
                    params.compute_target_charge()
                self.controller.set_constant_voltage(params.voltage_v, params.current_limit_a)
            elif params.mode == MeasurementMode.CV:
                self.controller.set_constant_voltage(params.scan_start_v, params.current_limit_a)
            else:
                raise ValueError(f"未対応のモードです: {params.mode}")

            self.controller.output(True)

            if params.mode == MeasurementMode.CV:
                for _ in range(max(1, params.cycles)):
                    for voltage_v in self._voltage_path(params.scan_start_v, params.scan_stop_v, params.scan_rate_v_per_s, params.sample_interval_s):
                        if self._stop_event.is_set():
                            break
                        # 出力ON中は電位値だけ更新する（MD0/VF の再送を避ける）
                        self.controller.update_output_voltage(voltage_v)
                        time.sleep(params.sample_interval_s)
                        measured_voltage = self.controller.read_voltage()
                        measured_current = self.controller.read_current()
                        elapsed = time.monotonic() - start_time
                        accumulated_charge += abs(measured_current) * params.sample_interval_s
                        point = MeasurementPoint(elapsed, measured_voltage, measured_current, accumulated_charge)
                        self.result.append(point)
                        self._emit("point", point=point)
                        if not within_limits(measured_voltage, measured_current, params.voltage_limit_v, params.current_limit_a):
                            out_of_limit_count += 1
                            if out_of_limit_count >= 3:
                                raise RuntimeError("安全制限を連続して超えました")
                        else:
                            out_of_limit_count = 0
                    if self._stop_event.is_set():
                        break
                # CV ループ正常完了（ユーザー停止でない場合）
                if not self._stop_event.is_set():
                    self.result.finished_reason = "completed"
                    self._emit("finished", reason="completed")
            else:
                while not self._stop_event.is_set():
                    time.sleep(params.sample_interval_s)
                    measured_voltage = self.controller.read_voltage()
                    measured_current = self.controller.read_current()
                    elapsed = time.monotonic() - start_time
                    if params.mode == MeasurementMode.CONSTANT_CURRENT:
                        accumulated_charge += abs(measured_current) * params.sample_interval_s
                    else:
                        accumulated_charge += abs(measured_current) * params.sample_interval_s
                    point = MeasurementPoint(elapsed, measured_voltage, measured_current, accumulated_charge)
                    self.result.append(point)
                    self._emit("point", point=point)
                    if not within_limits(measured_voltage, measured_current, params.voltage_limit_v, params.current_limit_a):
                        out_of_limit_count += 1
                        if out_of_limit_count >= 3:
                            raise RuntimeError("安全制限を連続して超えました")
                    else:
                        out_of_limit_count = 0
                    if ((params.mode == MeasurementMode.CONSTANT_CURRENT or params.mode == MeasurementMode.CONSTANT_VOLTAGE)
                            and params.stop_on_charge
                            and params.target_charge_c > 0
                            and accumulated_charge >= params.target_charge_c):
                        self.result.finished_reason = "target_charge"
                        self._emit("finished", reason="target_charge")
                        break
                    if elapsed >= params.max_duration_s:
                        self.result.finished_reason = "max_duration"
                        self._emit("finished", reason="max_duration")
                        break
        except Exception as exc:  # pragma: no cover - runtime error path
            self.result.finished_reason = f"error: {exc}"
            self._emit("error", message=str(exc))
        finally:
            # H コマンド（HOLD）のみ送信：電流源は即座に開回路（高インピーダンス）になる。
            # 0A/0V を印加してから HOLD すると試料（特にインターカレーション系）に
            # 不要な電位が加わるため、直接 HOLD で回路を切る。
            self.controller.output(False)
            self._emit("status", message="測定を終了しました")

    def _voltage_path(self, start_v: float, stop_v: float, rate_v_per_s: float, sample_interval_s: float):
        step = max(1e-6, abs(rate_v_per_s) * sample_interval_s)
        if start_v <= stop_v:
            voltage = start_v
            while voltage <= stop_v:
                yield voltage
                voltage += step
            voltage = stop_v
            while voltage >= start_v:
                yield voltage
                voltage -= step
        else:
            voltage = start_v
            while voltage >= stop_v:
                yield voltage
                voltage -= step
            voltage = stop_v
            while voltage <= start_v:
                yield voltage
                voltage += step


def save_measurement_csv(
    path: Path,
    result: MeasurementResult,
    metadata: dict | None = None,
) -> None:
    """CSVにデータとメタデータを保存する。

    metadata には測定条件や日時などを渡す。
    CSV 先頭に ``# key: value`` 形式でコメント行として書き込まれる。
    """
    import csv
    from datetime import datetime

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)

        # メタデータヘッダ
        writer.writerow(["# Electrochemistry R6244 Measurement Log"])
        writer.writerow([f"# Saved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
        if metadata:
            for key, value in metadata.items():
                writer.writerow([f"# {key}: {value}"])
        writer.writerow([f"# Points: {len(result.time_s)}"])
        writer.writerow([f"# Finished reason: {result.finished_reason}"])
        writer.writerow([""])  # 空行

        # データ
        writer.writerow(["time_s", "voltage_v", "current_a", "charge_c"])
        for row in zip(result.time_s, result.voltage_v, result.current_a, result.charge_c):
            writer.writerow(row)