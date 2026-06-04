import sys
import time
from pathlib import Path

# src フォルダを sys.path に追加
SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.core import (
    SimulatedR6244Device,
    ElectrochemistryController,
    MeasurementManager,
    MeasurementParameters,
    MeasurementMode
)

def test_cv_target_charge_stop():
    print("Testing target charge stop in CONSTANT_VOLTAGE mode (Simulation)...")
    sim_device = SimulatedR6244Device(resistance_ohm=10.0) # 10 ohm
    controller = ElectrochemistryController(sim_device)
    manager = MeasurementManager(controller)
    
    # 1.0 V constant voltage -> ~0.1 A current
    # target charge is 0.03 C. With sample interval of 0.1 s:
    # 0.1 A * 0.1 s = 0.01 C per step.
    # Should take about 3-4 steps (~0.3-0.4 s) to stop.
    params = MeasurementParameters(
        mode=MeasurementMode.CONSTANT_VOLTAGE,
        sample_interval_s=0.1,
        max_duration_s=5.0, # max 5 seconds
        voltage_v=1.0,
        current_limit_a=1.0,
        voltage_limit_v=10.0,
        stop_on_charge=True,
        target_charge_c=0.03 # target coulomb limit
    )
    
    print("Starting constant voltage measurement with target charge stop...")
    manager.start(params)
    
    # Wait for measurement thread to finish
    timeout = 5.0
    start_t = time.time()
    while manager._thread and manager._thread.is_alive():
        time.sleep(0.1)
        if time.time() - start_t > timeout:
            print("[FAIL] Timeout waiting for measurement thread!")
            sys.exit(1)
            
    print("Measurement thread finished.")
    result = manager.result
    print(f"  Finished reason: {result.finished_reason}")
    print(f"  Points collected: {len(result.time_s)}")
    print(f"  Accumulated charge: {result.charge_c[-1] if result.charge_c else 0} C")
    
    assert result.finished_reason == "target_charge", f"Unexpected finished reason: {result.finished_reason}"
    assert len(result.time_s) > 0, "No data points collected!"
    assert len(result.time_s) < 15, f"Took too many points: {len(result.time_s)} - didn't stop in time?"
    print("[OK] Constant voltage target charge stop verified successfully!")

if __name__ == "__main__":
    try:
        test_cv_target_charge_stop()
        print("\nAutomated target charge verification test PASSED!")
    except Exception as e:
        print(f"\nVerification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
