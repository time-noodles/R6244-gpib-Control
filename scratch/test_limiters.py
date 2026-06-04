import sys
from pathlib import Path

# src フォルダを sys.path に追加
SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.core import (
    R6244Device,
    R6244Commands,
    SimulatedR6244Device,
    ElectrochemistryController,
    MeasurementManager,
    MeasurementParameters,
    MeasurementMode
)

def test_device_mock():
    print("Testing command generation on R6244Device (mock/dry run)...")
    commands = R6244Commands()
    device = R6244Device(commands=commands)
    
    # We will subclass R6244Device to intercept _write calls without pyvisa
    sent_commands = []
    def dummy_write(text):
        print(f"  [WRITTEN] {text}")
        sent_commands.append(text)
    
    device._write = dummy_write
    device._state.connected = True
    
    controller = ElectrochemistryController(device)
    
    # 1. Test constant voltage (should set current limit)
    print("\nSetting constant voltage to 1.5 V, limit 0.005 A:")
    controller.set_constant_voltage(1.5, 0.005)
    
    # Check if basic commands are sent
    assert "MD0" in sent_commands, "MD0 command not found!"
    assert "VF" in sent_commands, "VF command not found!"
    assert "D 0.005A" in sent_commands, "D 0.005A command not found!"
    assert "D 1.5V" in sent_commands, "D {V}V command not found!"
    print("[OK] Constant voltage command generation verified.")
    
    # 2. Test constant current (should set voltage limit)
    sent_commands.clear()
    print("\nSetting constant current to 0.001 A, limit 5.0 V:")
    controller.set_constant_current(0.001, 5.0)
    
    # Check if basic commands are sent
    assert "MD0" in sent_commands, "MD0 command not found!"
    assert "IF" in sent_commands, "IF command not found!"
    assert "D 5.0V" in sent_commands, "D 5.0V command not found!"
    assert "D 1000UA" in sent_commands, "D {I}UA command not found!"
    print("[OK] Constant current command generation verified.")

    # 3. Test constant voltage with range commands
    sent_commands.clear()
    device.commands.current_range_cmd = "R1"
    device.commands.voltage_range_cmd = "AUTO"
    print("\nSetting constant voltage with range commands (current=R1, voltage=AUTO):")
    controller.set_constant_voltage(1.5, 0.005)
    assert "MD0" in sent_commands, "MD0 command not found!"
    assert "VF" in sent_commands, "VF command not found!"
    assert "D 0.005A" in sent_commands, "D 0.005A command not found!"
    # F2 then R1 for current range
    assert "F2" in sent_commands, "F2 command not found!"
    assert "R1" in sent_commands, "R1 command not found!"
    # F1 then R0 for AUTO voltage range
    assert "F1" in sent_commands, "F1 command not found!"
    assert "R0" in sent_commands, "R0 command not found!"
    assert "D 1.5V" in sent_commands, "D {V}V command not found!"
    print("[OK] Range command generation verified.")


def test_simulation_run():
    print("\nTesting simulation run with MeasurementManager...")
    sim_device = SimulatedR6244Device()
    controller = ElectrochemistryController(sim_device)
    manager = MeasurementManager(controller)
    
    # Define parameters for CV mode
    params = MeasurementParameters(
        mode=MeasurementMode.CV,
        sample_interval_s=0.1,
        scan_start_v=-0.5,
        scan_stop_v=0.5,
        scan_rate_v_per_s=0.2,
        cycles=1,
        current_limit_a=0.002,
        voltage_limit_v=1.0
    )
    
    print("Starting CV measurement run...")
    manager.start(params)
    
    # Wait for measurement thread to finish
    import time
    timeout = 10.0
    start_t = time.time()
    while manager._thread and manager._thread.is_alive():
        time.sleep(0.2)
        if time.time() - start_t > timeout:
            print("[FAIL] Timeout waiting for measurement thread!")
            sys.exit(1)
            
    print("Measurement thread finished.")
    result = manager.result
    print(f"Points collected: {len(result.time_s)}")
    assert len(result.time_s) > 0, "No data collected!"
    print("[OK] Simulation run completed successfully with no exceptions.")


def test_debounce_check():
    print("\nTesting safety limit debounce check...")
    class MockDevice(SimulatedR6244Device):
        def __init__(self):
            super().__init__()
            self.read_count = 0

        def read_current(self):
            self.read_count += 1
            # We violate limit on specific reads:
            # e.g., read 1: normal, read 2: violated, read 3: normal, read 4: violated, read 5: violated, read 6: violated (should abort)
            if self.read_count == 2:
                return 0.1 # Limit is 0.002 A, so this violates it
            elif self.read_count in (4, 5, 6):
                return 0.1 # 3 consecutive violations (reads 4, 5, 6)
            return 0.001

    dev = MockDevice()
    controller = ElectrochemistryController(dev)
    manager = MeasurementManager(controller)
    params = MeasurementParameters(
        mode=MeasurementMode.CONSTANT_VOLTAGE,
        sample_interval_s=0.01,
        max_duration_s=10.0,
        voltage_v=1.0,
        current_limit_a=0.002,
        voltage_limit_v=10.0,
        stop_on_charge=False
    )
    
    manager.start(params)
    
    # Wait for the thread to finish
    import time
    timeout = 5.0
    start_t = time.time()
    while manager._thread and manager._thread.is_alive():
        time.sleep(0.05)
        if time.time() - start_t > timeout:
            print("[FAIL] Timeout waiting for debounce thread!")
            sys.exit(1)
            
    print(f"Finished reason: {manager.result.finished_reason}")
    assert "安全制限を連続して超えました" in manager.result.finished_reason, "Should abort due to consecutive limits"
    # Read count should be 6 because:
    # read 1: 0.001 (OK)
    # read 2: 0.1 (Violate 1, count=1)
    # read 3: 0.001 (OK, count=0)
    # read 4: 0.1 (Violate 1, count=1)
    # read 5: 0.1 (Violate 2, count=2)
    # read 6: 0.1 (Violate 3, count=3 -> Abort!)
    assert dev.read_count == 6, f"Expected 6 reads, got {dev.read_count}"
    print("[OK] Debounce check successfully verified.")


if __name__ == "__main__":
    try:
        test_device_mock()
        test_simulation_run()
        test_debounce_check()
        print("\nAll automated verification tests PASSED!")
    except Exception as e:
        print(f"\nVerification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
