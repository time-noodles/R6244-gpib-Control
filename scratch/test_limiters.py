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
    
    # 1. Test constant voltage (should set IL)
    print("\nSetting constant voltage to 1.5 V, limit 0.005 A:")
    controller.set_constant_voltage(1.5, 0.005)
    
    # Check if IL0.005 was sent
    assert "IL0.005" in sent_commands, "IL command not found!"
    assert "D 1.5V" in sent_commands, "D {V}V command not found!"
    assert "IRN0" in sent_commands, "IRN0 command not found!"
    print("[OK] Constant voltage command generation verified.")
    
    # 2. Test constant current (should set VL)
    sent_commands.clear()
    print("\nSetting constant current to 0.001 A, limit 5.0 V:")
    controller.set_constant_current(0.001, 5.0)
    
    # Check if VL5.0 was sent
    assert "VL5.0" in sent_commands, "VL command not found!"
    assert "D 1000UA" in sent_commands, "D {I}UA command not found!"
    assert "VRN0" in sent_commands, "VRN0 command not found!"
    print("[OK] Constant current command generation verified.")


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


if __name__ == "__main__":
    try:
        test_device_mock()
        test_simulation_run()
        print("\nAll automated verification tests PASSED!")
    except Exception as e:
        print(f"\nVerification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
