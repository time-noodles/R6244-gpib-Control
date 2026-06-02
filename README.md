# Electrochemistry Control App - R6244

Agilent 82357A 経由で GPIB 接続された R6244 を操作するための、Python GUI アプリケーションおよびライブラリです。

## できること

- 定電流測定
- 定電位測定
- CV 測定
- 測定中の動的グラフ表示
- 測定パラメータ入力
- 重量と組成式からモル数を計算し、必要電気量で自動停止
- GPIB アドレスの GUI 入力
- 複数デバイスへの対応（各デバイスで GPIB アドレスを指定）

## インストール

### オンライン インストール（推奨）

```bash
pip install -e .
```

### オフライン インストール

```powershell
setup/install_offline.ps1
```

## 起動

### GUI アプリ起動

```powershell
python src/main.py
```

または、インストール後：

```bash
electrochemistry-r6244
```

### 別デバイスでの実行

config ファイルで GPIB アドレスを変更するか、GUI で接続時に入力します。

**例：別デバイス用設定**

```bash
python src/main.py --config config/device_config_example.json
```

または手動で config/default_config.json の `resource_name` を変更：

```json
{
  "device": {
    "mode": "real",
    "resource_name": "GPIB::1",
    ...
  }
}
```

## ライブラリ使用例

Python スクリプトから直接使用できます：

```python
from app.core import (
    R6244Device,
    R6244Commands,
    ElectrochemistryController,
)

# デバイス初期化
commands = R6244Commands()
device = R6244Device(commands=commands, timeout_ms=5000)
controller = ElectrochemistryController(device)

# 接続
state = controller.connect("GPIB::19")
print(f"Connected: {state.resource_name}")

# 定電流測定
controller.set_constant_current(0.001)  # 1 mA
controller.output(True)

# 測定
voltage = controller.read_voltage()
current = controller.read_current()

# 停止
controller.output(False)
controller.disconnect()
```

詳細は `examples/basic_usage.py` を参照してください。

## コマンドセット（R6244）

| コマンド | 説明 |
|---------|------|
| C | デバイスクリア |
| MD0 | DC 動作モード |
| VF | 定電位モード設定 |
| IF | 定電流モード設定 |
| D{value}UA | 電流設定（uA 単位） |
| D{value}V | 電位設定（V 単位） |
| E | 出力 ON |
| H | ホールド（出力 OFF） |
| F1 | 電位測定クエリ |
| F2 | 電流測定クエリ |

## 補足

RDKit を必須依存とします。分子量計算と原子量は RDKit の周期表を使って算出します。オフライン配布する場合は対応する RDKit の wheel を `pyvisa_pkgs/` に含めてください（Windows + Python バージョンに依存します）。

## マルチデバイス対応

複数の R6244 デバイスで運用する場合：

1. 各デバイスに異なる GPIB アドレスを設定
2. 各デバイス用に別の config ファイルを作成
3. GUI の "GPIB Address / Resource" フィールドで指定、または起動時に config を指定

**例：**

```bash
# デバイス 1
python src/main.py --config config/device_config_1.json

# デバイス 2（別ウィンドウ）
python src/main.py --config config/device_config_2.json
```