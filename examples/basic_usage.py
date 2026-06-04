#!/usr/bin/env python
"""
Example usage of electrochemistry-r6244 library

This script demonstrates how to use the R6244 control library
for different measurement modes.
"""

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.core import (
    R6244Device,
    R6244Commands,
    ElectrochemistryController,
)
import time


def example_constant_current(resource_name="GPIB::19"):
    """Example: Constant current measurement"""
    
    print("=" * 60)
    print("Example: Constant Current Measurement")
    print("=" * 60)
    
    # Setup device
    commands = R6244Commands()
    device = R6244Device(commands=commands, timeout_ms=5000)
    controller = ElectrochemistryController(device)
    
    # Connect to device
    try:
        state = controller.connect(resource_name)
        print(f"✓ Connected: {state.resource_name}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return
    
    try:
        # Set constant current mode
        current_a = 0.001  # 1 mA
        controller.set_constant_current(current_a, 10.0)
        print(f"✓ Set constant current: {current_a} A")
        
        # Enable output
        controller.output(True)
        print("✓ Output enabled")
        
        # Measure for 10 seconds
        for i in range(10):
            time.sleep(1)
            voltage = controller.read_voltage()
            current = controller.read_current()
            print(f"  [{i+1}s] V={voltage:.6f} V, I={current:.6e} A")
        
        # Disable output
        controller.output(False)
        print("✓ Output disabled")
        
    finally:
        controller.disconnect()
        print("✓ Disconnected")


def example_constant_voltage(resource_name="GPIB::19"):
    """Example: Constant voltage measurement"""
    
    print("\n" + "=" * 60)
    print("Example: Constant Voltage Measurement")
    print("=" * 60)
    
    # Setup device
    commands = R6244Commands()
    device = R6244Device(commands=commands, timeout_ms=5000)
    controller = ElectrochemistryController(device)
    
    # Connect to device
    try:
        state = controller.connect(resource_name)
        print(f"✓ Connected: {state.resource_name}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return
    
    try:
        # Set constant voltage mode
        voltage_v = 1.0  # 1 V
        controller.set_constant_voltage(voltage_v, 0.01)
        print(f"✓ Set constant voltage: {voltage_v} V")
        
        # Enable output
        controller.output(True)
        print("✓ Output enabled")
        
        # Measure for 10 seconds
        for i in range(10):
            time.sleep(1)
            voltage = controller.read_voltage()
            current = controller.read_current()
            print(f"  [{i+1}s] V={voltage:.6f} V, I={current:.6e} A")
        
        # Disable output
        controller.output(False)
        print("✓ Output disabled")
        
    finally:
        controller.disconnect()
        print("✓ Disconnected")


def main():
    """Run examples"""
    
    print("\nR6244 Control Library - Examples")
    print("=" * 60)
    
    resource = input("Enter GPIB resource name (default GPIB::19): ").strip()
    if not resource:
        resource = "GPIB::19"
    
    choice = input("\nSelect example:\n1. Constant current\n2. Constant voltage\nChoice (1 or 2): ").strip()
    
    if choice == "1":
        example_constant_current(resource)
    elif choice == "2":
        example_constant_voltage(resource)
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
