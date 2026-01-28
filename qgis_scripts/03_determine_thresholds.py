import os
import math
from qgis.core import QgsProject

print("=========== QUANTILE ANALYSIS START ===========")

# ---- 0. パス設定 (相対パス化) ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 読み込み・書き込みが必要な場合の基準ディレクトリ
BASE_DIR = os.path.join(SCRIPT_DIR, "data", "processed")

# 出力先が必要な場合に備え自動生成
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

# --------- 1. 入力レイヤを取得 ---------
LAYER_NAME = "risk_proxy_5m"

layers = QgsProject.instance().mapLayersByName(LAYER_NAME)
if not layers:
    raise RuntimeError(f"レイヤ '{LAYER_NAME}' が見つかりません")

layer = layers[0]
provider = layer.dataProvider()

# ラスタブロックの取得
block = provider.block(1, layer.extent(), layer.width(), layer.height())
nodata = provider.sourceNoDataValue(1)

values = []
for r in range(block.height()):
    for c in range(block.width()):
        v = block.value(c, r)
        if v is None:
            continue
        if nodata is not None and v == nodata:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        values.append(float(v))

if not values:
    raise RuntimeError("値が1つも取れませんでした。有効なデータがあるか確認してください。")

values.sort()
n = len(values)

def quantile(p):
    # 0〜1 の p に対する補間付き分位点
    if p <= 0:
        return values[0]
    if p >= 1:
        return values[-1]
    k = (n - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    return values[f] + (values[c] - values[f]) * (k - f)

print(f"▶ 対象レイヤ: {LAYER_NAME}")
print("n:", n)
print("min:", values[0], "max:", values[-1])
for p in (0.30, 0.50, 0.70):
    print(f"q{int(p*100)}:", quantile(p))

print("=========== QUANTILE ANALYSIS DONE ===========")
