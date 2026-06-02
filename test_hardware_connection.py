#!/usr/bin/env python
"""
実物テスト: GPIB 接続確認スクリプト

このスクリプトは以下を確認します：
1. pyvisa が利用可能か
2. GPIB デバイスへの接続
3. IDN クエリ（機器識別）
4. 基本的な通信動作
"""

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.core import R6244Device, R6244Commands


def test_pyvisa():
    """pyvisa の利用可能性確認"""
    try:
        import pyvisa
        print("✓ pyvisa は利用可能です")
        print(f"  バージョン: {pyvisa.__version__}")
        
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        print(f"✓ 検出されたリソース: {resources if resources else '(なし)'}")
        rm.close()
        return True
    except ImportError as e:
        print(f"✗ pyvisa をインストール必要があります: {e}")
        return False
    except Exception as e:
        print(f"✗ pyvisa エラー: {e}")
        return False


def test_gpib_connection(resource_name: str, timeout_ms: int = 5000):
    """GPIB デバイス接続テスト"""
    print(f"\n接続テスト: {resource_name}")
    print(f"タイムアウト: {timeout_ms} ms")
    
    device = R6244Device(timeout_ms=timeout_ms)
    
    try:
        state = device.connect(resource_name)
        print(f"✓ 接続成功")
        print(f"  状態: {state}")
        
        # IDN クエリ
        print(f"\nIDN クエリを実行中...")
        idn = device.identify()
        print(f"✓ IDN 応答: {idn}")
        
        device.disconnect()
        print(f"✓ 切断完了")
        return True
        
    except Exception as e:
        print(f"✗ 接続エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("R6244 GPIB 接続テスト")
    print("=" * 60)
    
    # pyvisa 確認
    if not test_pyvisa():
        print("\n✗ テスト中止: pyvisa が利用できません")
        sys.exit(1)
    
    # ユーザー入力
    print("\n" + "=" * 60)
    print("GPIB リソース設定")
    print("=" * 60)
    
    default_resource = "GPIB0::1::INSTR"
    user_input = input(f"GPIB リソース名 (デフォルト: {default_resource}): ").strip()
    resource_name = user_input if user_input else default_resource
    
    user_timeout = input("タイムアウト (ms、デフォルト: 5000): ").strip()
    timeout_ms = int(user_timeout) if user_timeout else 5000
    
    # 接続テスト実行
    print("\n" + "=" * 60)
    success = test_gpib_connection(resource_name, timeout_ms)
    
    print("\n" + "=" * 60)
    if success:
        print("✓ すべてのテストが完了しました")
        sys.exit(0)
    else:
        print("✗ テストに失敗しました")
        print("\n確認事項:")
        print("  1. GPIB アダプタがコンピュータに接続されているか")
        print("  2. R6244 機器が電源オンになっているか")
        print("  3. ケーブルが正しく接続されているか")
        print("  4. GPIB アドレスが正しいか (通常は 1)")
        sys.exit(1)


if __name__ == "__main__":
    main()
