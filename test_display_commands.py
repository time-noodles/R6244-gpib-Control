#!/usr/bin/env python
"""
R6244 ディスプレイ表示コマンドテスト

このスクリプトは R6244 のディスプレイに電位・電流値を表示するコマンドを送信します。
"""

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.core import R6244Device, R6244Commands


def test_display_commands():
    """ディスプレイ表示コマンドをテスト"""
    
    print("=" * 60)
    print("R6244 ディスプレイ表示コマンドテスト")
    print("=" * 60)
    
    # コマンド設定
    commands = R6244Commands(
        idn_query="*IDN?",
        set_current_mode="SOUR:FUNC CURR",
        set_voltage_mode="SOUR:FUNC VOLT",
        set_current="SOUR:CURR {value}",
        set_voltage="SOUR:VOLT {value}",
        output_on="OUTP ON",
        output_off="OUTP OFF",
        measure_voltage="MEAS:VOLT?",
        measure_current="MEAS:CURR?",
        display_voltage="DISP:VOLT",
        display_current="DISP:CURR",
    )
    
    device = R6244Device(commands=commands, timeout_ms=5000)
    
    # 接続
    resource_name = input("GPIB リソース名 (例: GPIB0::1::INSTR): ").strip()
    if not resource_name:
        resource_name = "GPIB0::1::INSTR"
    
    try:
        print(f"\n接続中: {resource_name}")
        state = device.connect(resource_name)
        print(f"✓ 接続成功: {state.idn}")
        
        # ディスプレイ電位表示
        print("\n電位表示コマンド送信...")
        device.set_display_voltage()
        print("✓ コマンド送信: DISP:VOLT")
        
        input("R6244 のディスプレイを確認して Enter キーを押してください")
        
        # ディスプレイ電流表示
        print("\n電流表示コマンド送信...")
        device.set_display_current()
        print("✓ コマンド送信: DISP:CURR")
        
        input("R6244 のディスプレイを確認して Enter キーを押してください")
        
        print("\n✓ テスト完了")
        device.disconnect()
        
    except Exception as e:
        print(f"✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_display_commands()
