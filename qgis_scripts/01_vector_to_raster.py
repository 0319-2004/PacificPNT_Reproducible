exec(r"""
import os
import math
import processing
from qgis.core import QgsProject, QgsVectorLayer

print("=========== BUILDING RASTERIZATION (3m / 5m) START ===========")


# ---- 0. 入力レイヤを取得 ----
proj = QgsProject.instance()

# EPSG:6668 の元建物ポリゴン
BLD_SRC_NAME = "bld_2d"   # レイヤパネルの名前に合わせて変更
AOI_NAME     = "aoi"      # EPSG:6677 の AOI ポリゴン

bld_src_list = proj.mapLayersByName(BLD_SRC_NAME)
aoi_list     = proj.mapLayersByName(AOI_NAME)

if not bld_src_list:
    raise RuntimeError(f"建物レイヤ '{BLD_SRC_NAME}' が見つかりません")
if not aoi_list:
    raise RuntimeError(f"AOIレイヤ '{AOI_NAME}' が見つかりません")

bld_src = bld_src_list[0]
aoi     = aoi_list[0]

print(f"▶ 元建物レイヤ: {BLD_SRC_NAME}  ({bld_src.crs().authid()})")
print(f"▶ AOIレイヤ    : {AOI_NAME}  ({aoi.crs().authid()})")

# AOI と同じフォルダに出力する
aoi_path = aoi.dataProvider().dataSourceUri().split("|")[0]
BASE_DIR = os.path.dirname(aoi_path) if aoi_path else os.path.expanduser("~/Desktop")
print(f"▶ 出力フォルダ : {BASE_DIR}")


# ---- 1. 建物を EPSG:6677 に再投影 ----
bld_6677_path = os.path.join(BASE_DIR, "bld_6677.gpkg")
print("\n[*] 建物レイヤを EPSG:6677 に再投影します...")
params_reproj = {
    "INPUT": bld_src,
    "TARGET_CRS": "EPSG:6677",
    "OPERATION": "",
    "OUTPUT": bld_6677_path
}
processing.run("native:reprojectlayer", params_reproj)
print(f"[+] 再投影レイヤ: {bld_6677_path}")

# 読み込み
bld_6677 = QgsVectorLayer(bld_6677_path, "bld_6677", "ogr")
proj.addMapLayer(bld_6677)


# ---- 2. AOI 内にクリップ ----
bld_clip_path = os.path.join(BASE_DIR, "bld_clip.gpkg")
print("\n[*] AOI で建物をクリップします...")
params_clip = {
    "INPUT": bld_6677,
    "OVERLAY": aoi,
    "OUTPUT": bld_clip_path
}
processing.run("native:clip", params_clip)
print(f"[+] クリップ済み建物: {bld_clip_path}")

bld_clip = QgsVectorLayer(bld_clip_path, "bld_clip", "ogr")
proj.addMapLayer(bld_clip)


# ---- 3. AOI からラスタの行列数を決定 ----
extent = aoi.extent()
width_m  = extent.width()
height_m = extent.height()
print(f"\n▶ AOIサイズ: {width_m:.2f}m × {height_m:.2f}m")

def compute_raster_shape(pixel_size):
    cols = int(math.ceil(width_m  / pixel_size))
    rows = int(math.ceil(height_m / pixel_size))
    return cols, rows

cols3, rows3 = compute_raster_shape(3.0)
cols5, rows5 = compute_raster_shape(5.0)
print(f"▶ 3m解像度: {cols3} 列 × {rows3} 行")
print(f"▶ 5m解像度: {cols5} 列 × {rows5} 行")

extent_str = f"{extent.xMinimum()},{extent.xMaximum()},{extent.yMinimum()},{extent.yMaximum()} [EPSG:6677]"


# ---- 4. gdal:rasterize で 3m と 5m の高さラスタを作成 ----
def rasterize_height(out_path, cols, rows, pixel_size, name):
    print(f"\n[*] {pixel_size:.1f}m ラスタ {name} を作成中...")
    params = {
        "INPUT": bld_clip_path,
        "FIELD": "measuredHeight",   # PLATEAU の高さ属性
        "BURN": 0,
        "UNITS": 1,                  # 1=ピクセル数指定（WIDTH/HEIGHT）
        "WIDTH": cols,
        "HEIGHT": rows,
        "EXTENT": extent_str,
        "NODATA": 0,
        "OPTIONS": "",
        "DATA_TYPE": 5,             # Float32
        "INIT": 0,
        "INVERT": False,
        "OUTPUT": out_path
    }
    processing.run("gdal:rasterize", params)
    print(f"[+] 完了: {out_path}")

bld_3m_path = os.path.join(BASE_DIR, "bld_height_3m.tif")
bld_5m_path = os.path.join(BASE_DIR, "bld_height_5m.tif")

rasterize_height(bld_3m_path, cols3, rows3, 3.0, "bld_height_3m")
rasterize_height(bld_5m_path, cols5, rows5, 5.0, "bld_height_5m")

# 読み込み
for p, n in [(bld_3m_path, "bld_height_3m"), (bld_5m_path, "bld_height_5m")]:
    lyr = QgsRasterLayer(p, n)
    if lyr.isValid():
        proj.addMapLayer(lyr)
    else:
        print(f"⚠ ラスタの読み込みに失敗: {p}")

print("\n=========== BUILDING RASTERIZATION DONE ==========="")
)
