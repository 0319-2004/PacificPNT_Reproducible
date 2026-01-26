exec("""
from qgis.core import QgsProject, QgsRasterLayer
import processing
import math
import os

# ==== 入力設定 ====
RISK_LAYER_NAME = "risk_proxy_5m"   # ここはプロジェクト上のレイヤ名に合わせる
OUT_PATH = os.path.expanduser("~/Desktop/risk_class_5m_py.tif")

proj = QgsProject.instance()
layers = proj.mapLayersByName(RISK_LAYER_NAME)
if not layers:
    raise RuntimeError(f"レイヤ '{RISK_LAYER_NAME}' が見つかりません（レイヤパネルの名前と完全一致させて）")

risk_layer = layers[0]
risk_path = risk_layer.dataProvider().dataSourceUri().split("|")[0]

print("▶ INPUT:", risk_path)
print("▶ CRS:", risk_layer.crs().authid())
print("▶ Size:", risk_layer.width(), "x", risk_layer.height())

# ==== 値を全て読み取り、ECDF（分位点） ====
provider = risk_layer.dataProvider()
extent = risk_layer.extent()
cols = risk_layer.width()
rows = risk_layer.height()

block = provider.block(1, extent, cols, rows)
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

values.sort()
n = len(values)
if n == 0:
    raise RuntimeError("有効ピクセルが0です（入力がNoDataのみの可能性）。AOIマスク/入力レイヤを確認。")

def quantile(p):
    i = (n - 1) * p
    lo = math.floor(i)
    hi = math.ceil(i)
    if lo == hi:
        return values[int(i)]
    return values[lo] * (hi - i) + values[hi] * (i - lo)

q30 = quantile(0.30)
q70 = quantile(0.70)

print("n:", n)
print("min:", min(values), "max:", max(values))
print("q30:", q30, "q70:", q70)

# ==== 分類式（ANDを避けて掛け算で論理積） ====
expr = f"(A < {q30})*1 + ((A >= {q30})*(A < {q70}))*2 + (A >= {q70})*3"
print("▶ Expression:", expr)

params = {
    "INPUT_A": risk_path,
    "BAND_A": 1,
    "FORMULA": expr,
    "NO_DATA": 0,
    "OUTPUT": OUT_PATH
}

print("[*] running gdal:rastercalculator ...")
processing.run("gdal:rastercalculator", params)

print("[+] created:", OUT_PATH)
out_lyr = QgsRasterLayer(OUT_PATH, "risk_class_5m_py")
if not out_lyr.isValid():
    raise RuntimeError("出力ラスタの読み込みに失敗しました")
proj.addMapLayer(out_lyr)
print("[+] added layer: risk_class_5m_py")
""")

