#!/usr/bin/env python
"""
R6244 Command Debug Tool

This script helps debug command format issues by showing what
commands are being sent to the device.
"""

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.core import (
    R6244Device,
    R6244Commands,
    ElectrochemistryController,
)


def debug_commands():
    """Debug command format"""
    
    print("=" * 60)
    print("R6244 Command Debug Tool")
    print("=" * 60)
    
    # Setup device with debug mode
    commands = R6244Commands()
    device = R6244Device(commands=commands, timeout_ms=5000)
    device.debug_mode = True  # Enable debug output
    
    resource_name = input("GPIB resource (default GPIB::19): ").strip()
    if not resource_name:
        resource_name = "GPIB::19"
    
    try:
        print(f"\nConnecting to {resource_name}...")
        device.connect(resource_name)
        print("✓ Connected\n")
        
        controller = ElectrochemistryController(device)
        
        # Test 1: Constant Current
        print("\n" + "=" * 60)
        print("Test 1: Set Constant Current 0.01 A")
        print("=" * 60)
        current_a = 0.01
        print(f"\nSetting current to {current_a} A:")
        controller.set_constant_current(current_a)
        
        # Test 2: Constant Voltage  
        print("\n" + "=" * 60)
        print("Test 2: Set Constant Voltage 1.0 V")
        print("=" * 60)
        voltage_v = 1.0
        print(f"\nSetting voltage to {voltage_v} V:")
        controller.set_constant_voltage(voltage_v)
        
        # Test 3: Output ON
        print("\n" + "=" * 60)
        print("Test 3: Enable Output")
        print("=" * 60)
        print("\nEnabling output:")
        controller.output(True)
        
        # Test 4: Read Voltage
        print("\n" + "=" * 60)
        print("Test 4: Read Voltage")
        print("=" * 60)
        print("\nReading voltage:")
        v = controller.read_voltage()
        print(f"Result: {v} V")
        
        # Test 5: Read Current
        print("\n" + "=" * 60)
        print("Test 5: Read Current")
        print("=" * 60)
        print("\nReading current:")
        i = controller.read_current()
        print(f"Result: {i} A")
        
        # Test 6: Output OFF
        print("\n" + "=" * 60)
        print("Test 6: Disable Output")
        print("=" * 60)
        print("\nDisabling output:")
        controller.output(False)
        
        device.disconnect()
        print("\n✓ Disconnected")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    debug_commands()
