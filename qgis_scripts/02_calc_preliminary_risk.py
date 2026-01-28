import os
import processing
from qgis.core import QgsProject, QgsRasterLayer

print("=========== SKYVIEW PROXY VIA NEIGHBOR MAX START ===========")

# ---- 0. パス設定 (相対パス化) ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, "data", "processed")

# 出力先フォルダの自動生成
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)
    print(f"[*] ディレクトリを作成しました: {BASE_DIR}")

# --------- 1. 入力ラスタ（bld_height_5m）を取得 ---------
HEIGHT_LAYER_NAME = "bld_height_5m"   # レイヤ名

proj = QgsProject.instance()
layers = proj.mapLayersByName(HEIGHT_LAYER_NAME)
if not layers:
    raise FileNotFoundError(f"レイヤ '{HEIGHT_LAYER_NAME}' が見つかりません。")

height_layer = layers[0]
# 入力ファイルパス（QGIS上のレイヤから取得するが、出力はBASE_DIRに固定）
height_path = height_layer.dataProvider().dataSourceUri().split('|')[0]

print(f"▶ 使用建物高さラスタ: {height_path}")
print(f"▶ CRS: {height_layer.crs().authid()}")

cell_size_x = height_layer.rasterUnitsPerPixelX()
cell_size_y = height_layer.rasterUnitsPerPixelY()
print(f"▶ セルサイズ: {cell_size_x:.3f} m × {cell_size_y:.3f} m")


# --------- 2. r.neighbors で局所最大高さ（30m近傍） ---------
RADIUS_M = 30.0
kernel_half = max(1, int(round(RADIUS_M / cell_size_x)))
kernel_size = kernel_half * 2 + 1   # 奇数に

print(f"▶ 近傍半径 ~{RADIUS_M:.1f} m → カーネルサイズ = {kernel_size} セル")

localmax_path = os.path.join(BASE_DIR, "bld_height_5m_localmax.tif")

print("[*] GRASS r.neighbors で局所最大高さを計算中...")
params_neighbors = {
    "input": height_path,
    "selection": None,
    "method": 6,      # 6 = maximum
    "size": kernel_size,
    "quantile": 0.5,
    "weight": "",
    "output": localmax_path,
    "GRASS_REGION_PARAMETER": None,
    "GRASS_REGION_CELLSIZE_PARAMETER": 0,
    "GRASS_RASTER_FORMAT_OPT": "",
    "GRASS_RASTER_FORMAT_META": ""
}
processing.run("grass7:r.neighbors", params_neighbors)
print(f"[+] 局所最大高さラスタを作成: {localmax_path}")

localmax_layer = QgsRasterLayer(localmax_path, "bld_height_5m_localmax")
if localmax_layer.isValid():
    proj.addMapLayer(localmax_layer)
else:
    raise RuntimeError("局所最大高さラスタの読み込みに失敗しました。")


# --------- 3. H_global_max を取得 ---------
stats = localmax_layer.dataProvider().bandStatistics(1)
H_global_max = stats.maximumValue
if H_global_max <= 0:
    raise RuntimeError(f"H_global_max が 0 以下です: {H_global_max}")
print(f"▶ H_global_max (局所最大高さの最大値) = {H_global_max:.3f} m")


# --------- 4. risk_proxy, svf_proxy を 0〜1 で作成 ---------
risk_path = os.path.join(BASE_DIR, "risk_proxy_5m.tif")
svf_path  = os.path.join(BASE_DIR, "svf_proxy_5m.tif")

print("[*] GDAL Raster Calculator で risk_proxy = H_local_max / H_global_max を計算中...")
expr_risk = f"A/{H_global_max}"

params_risk = {
    "INPUT_A": localmax_path,
    "BAND_A": 1,
    "INPUT_B": None, "BAND_B": -1,
    "INPUT_C": None, "BAND_C": -1,
    "INPUT_D": None, "BAND_D": -1,
    "INPUT_E": None, "BAND_E": -1,
    "INPUT_F": None, "BAND_F": -1,
    "FORMULA": expr_risk,
    "NO_DATA": 0,
    "RTYPE": 5,   # Float32
    "EXTRA": "",
    "OUTPUT": risk_path
}
processing.run("gdal:rastercalculator", params_risk)
print(f"[+] risk_proxy_5m.tif を作成: {risk_path}")

print("[*] svf_proxy = 1 - risk_proxy を計算中...")
params_svf = {
    "INPUT_A": risk_path,
    "BAND_A": 1,
    "INPUT_B": None, "BAND_B": -1,
    "INPUT_C": None, "BAND_C": -1,
    "INPUT_D": None, "BAND_D": -1,
    "INPUT_E": None, "BAND_E": -1,
    "INPUT_F": None, "BAND_F": -1,
    "FORMULA": "1 - A",
    "NO_DATA": 0,
    "RTYPE": 5,
    "EXTRA": "",
    "OUTPUT": svf_path
}
processing.run("gdal:rastercalculator", params_svf)
print(f"[+] svf_proxy_5m.tif を作成: {svf_path}")


# --------- 5. 結果レイヤを追加 ---------
risk_layer = QgsRasterLayer(risk_path, "risk_proxy_5m")
svf_layer  = QgsRasterLayer(svf_path,  "svf_proxy_5m")

for lyr in (risk_layer, svf_layer):
    if lyr.isValid():
        proj.addMapLayer(lyr)
    else:
        print(f"⚠ レイヤの読み込みに失敗: {lyr.name()}")

print("=========== SKYVIEW PROXY VIA NEIGHBOR MAX DONE ===========")
