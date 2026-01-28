import os
import math
import processing
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer

def run_rasterization(output_dir, bld_src_name="bld_2d", aoi_name="aoi"):
    """
    建物のベクトルデータを再投影・クリップし、指定された解像度でラスタライズする。
    """
    print("=========== BUILDING RASTERIZATION (3m / 5m) START ===========")
    
    # 出力先フォルダの自動生成
    os.makedirs(output_dir, exist_ok=True)
    
    proj = QgsProject.instance()

    # ---- 1. 入力レイヤを取得 ----
    bld_src_list = proj.mapLayersByName(bld_src_name)
    aoi_list = proj.mapLayersByName(aoi_name)

    if not bld_src_list:
        raise RuntimeError(f"建物レイヤ '{bld_src_name}' が見つかりません")
    if not aoi_list:
        raise RuntimeError(f"AOIレイヤ '{aoi_name}' が見つかりません")

    bld_src = bld_src_list[0]
    aoi = aoi_list[0]

    print(f"▶ 元建物レイヤ: {bld_src_name} ({bld_src.crs().authid()})")
    print(f"▶ AOIレイヤ    : {aoi_name} ({aoi.crs().authid()})")
    print(f"▶ 出力フォルダ : {output_dir}")

    # ---- 2. 建物を EPSG:6677 に再投影 ----
    bld_6677_path = os.path.join(output_dir, "bld_6677.gpkg")
    print("\n[*] 建物レイヤを EPSG:6677 に再投影します...")
    params_reproj = {
        "INPUT": bld_src,
        "TARGET_CRS": "EPSG:6677",
        "OPERATION": "",
        "OUTPUT": bld_6677_path
    }
    processing.run("native:reprojectlayer", params_reproj)
    
    bld_6677 = QgsVectorLayer(bld_6677_path, "bld_6677", "ogr")
    proj.addMapLayer(bld_6677)

    # ---- 3. AOI 内にクリップ ----
    bld_clip_path = os.path.join(output_dir, "bld_clip.gpkg")
    print("\n[*] AOI で建物をクリップします...")
    params_clip = {
        "INPUT": bld_6677,
        "OVERLAY": aoi,
        "OUTPUT": bld_clip_path
    }
    processing.run("native:clip", params_clip)
    
    bld_clip = QgsVectorLayer(bld_clip_path, "bld_clip", "ogr")
    proj.addMapLayer(bld_clip)

    # ---- 4. AOI からラスタの行列数を決定 ----
    extent = aoi.extent()
    width_m = extent.width()
    height_m = extent.height()
    
    def compute_raster_shape(pixel_size):
        cols = int(math.ceil(width_m / pixel_size))
        rows = int(math.ceil(height_m / pixel_size))
        return cols, rows

    cols3, rows3 = compute_raster_shape(3.0)
    cols5, rows5 = compute_raster_shape(5.0)
    extent_str = f"{extent.xMinimum()},{extent.xMaximum()},{extent.yMinimum()},{extent.yMaximum()} [EPSG:6677]"

    # ---- 5. gdal:rasterize 実行関数 ----
    def rasterize_height(out_path, cols, rows, pixel_size, name):
        print(f"\n[*] {pixel_size:.1f}m ラスタ {name} を作成中...")
        params = {
            "INPUT": bld_clip_path,
            "FIELD": "measuredHeight",
            "BURN": 0,
            "UNITS": 1,
            "WIDTH": cols,
            "HEIGHT": rows,
            "EXTENT": extent_str,
            "NODATA": 0,
            "OPTIONS": "",
            "DATA_TYPE": 5,
            "INIT": 0,
            "INVERT": False,
            "OUTPUT": out_path
        }
        processing.run("gdal:rasterize", params)

    bld_3m_path = os.path.join(output_dir, "bld_height_3m.tif")
    bld_5m_path = os.path.join(output_dir, "bld_height_5m.tif")

    rasterize_height(bld_3m_path, cols3, rows3, 3.0, "bld_height_3m")
    rasterize_height(bld_5m_path, cols5, rows5, 5.0, "bld_height_5m")

    # 読み込み
    for p, n in [(bld_3m_path, "bld_height_3m"), (bld_5m_path, "bld_height_5m")]:
        lyr = QgsRasterLayer(p, n)
        if lyr.isValid():
            proj.addMapLayer(lyr)
        else:
            print(f"⚠ ラスタの読み込みに失敗: {p}")

    print("\n=========== BUILDING RASTERIZATION DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: qgis_scripts/ (Rootから1階層深い)
    # ルールに基づき ../data/processed を構築
    base_dir = os.path.dirname(os.path.abspath(__file__))
    processed_data_dir = os.path.join(base_dir, "..", "data", "processed")
    
    # 処理実行
    run_rasterization(
        output_dir=processed_data_dir,
        bld_src_name="bld_2d",
        aoi_name="aoi"
    )
