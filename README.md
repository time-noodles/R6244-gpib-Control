# Electrochemistry Control App

Agilent 82357A 経由で GPIB 接続された R6244 を操作するための、オフライン前提の Python GUI アプリです。

## できること

- 定電流測定
- 定電位測定
- CV 測定
- 測定中の動的グラフ表示
- 測定パラメータ入力
- 重量と組成式からモル数を計算し、必要電気量で自動停止
- GPIB アドレスの GUI 入力
- シミュレーションモードでの動作確認

## 起動

```powershell
python src/main.py
```

## オフライン導入

`setup/install_offline.ps1` を実行すると、`pyvisa_pkgs/` の wheel を使って依存を入れます。

## 補足

R6244 の実コマンドは機器仕様に依存するため、`config/default_config.json` のコマンド設定は必要に応じて調整してください。
RDKit を必須依存にします。分子量計算と原子量は RDKit の周期表を使って算出します。オフライン配布する場合は対応する RDKit の wheel を `pyvisa_pkgs/` に含めてください（Windows + Python バージョンに依存します）。