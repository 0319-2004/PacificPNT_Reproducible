import os
import math
import processing
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer

def get_or_load_layer(layer_name, file_path):
    """
    QGIS上に指定した名前のレイヤがあればそれを返す。
    なければ file_path からロードしてプロジェクトに追加する。
    """
    proj = QgsProject.instance()
    layers = proj.mapLayersByName(layer_name)
    
    if layers:
        print(f"✔ 既存レイヤを使用: {layer_name}")
        return layers[0]
    
    if not os.path.exists(file_path):
        # 橋データなどは「無くても進む」場合があるので、ここではNoneを返さずエラーにするか、
        # 呼び出し元で制御する。今回は「必須ファイルが見つからない」としてエラーにする。
        # ただし、橋ファイルは「あれば処理する」方針にするため、呼び出し元でチェック推奨だが、
        # ここではシンプルにファイルパスチェックを行う。
        return None
    
    print(f"📂 ファイルからロード中: {os.path.basename(file_path)}")
    layer = QgsVectorLayer(file_path, layer_name, "ogr")
    
    if not layer.isValid():
        return None
    
    proj.addMapLayer(layer)
    return layer

def run_rasterization(output_dir, bld_path, brid_path, aoi_path):
    """
    建物・橋データをAOIでクリップ・再投影し、建物はラスタライズする。
    """
    print("=========== DATA PREPROCESSING (Bldg & Bridge) START ===========")
    
    os.makedirs(output_dir, exist_ok=True)
    proj = QgsProject.instance()

    # ---- 1. AOIの準備 (読み込み & 座標変換) ----
    aoi_origin = get_or_load_layer("aoi", aoi_path)
    if not aoi_origin:
         raise RuntimeError(f"❌ AOIファイルが見つかりません: {aoi_path}")

    print(f"▶ 元AOIレイヤ : {aoi_origin.name()} ({aoi_origin.crs().authid()})")

    # EPSG:6677 に変換
    print("\n[*] AOIレイヤを EPSG:6677 に再投影します...")
    params_aoi_reproj = {
        "INPUT": aoi_origin,
        "TARGET_CRS": "EPSG:6677",
        "OUTPUT": "TEMPORARY_OUTPUT"
    }
    result_aoi = processing.run("native:reprojectlayer", params_aoi_reproj)
    aoi_6677 = result_aoi['OUTPUT']
    aoi = aoi_6677 # 以降はこれを使う

    # ---- 2. 建物の処理 (再投影 -> クリップ -> ラスタライズ) ----
    bld_src = get_or_load_layer("bld_2d", bld_path)
    bld_clip_path = os.path.join(output_dir, "bld_clip.gpkg")

    if bld_src:
        print(f"\n▶ 建物レイヤ処理中: {bld_src.name()}")
        
        # 再投影
        bld_6677_path = os.path.join(output_dir, "bld_6677.gpkg")
        print("  [*] 建物を再投影中...")
        processing.run("native:reprojectlayer", {
            "INPUT": bld_src, "TARGET_CRS": "EPSG:6677", "OUTPUT": bld_6677_path
        })
        bld_6677 = QgsVectorLayer(bld_6677_path, "bld_6677", "ogr")
        
        # クリップ
        print("  [*] 建物をAOIでクリップ中...")
        processing.run("native:clip", {
            "INPUT": bld_6677, "OVERLAY": aoi, "OUTPUT": bld_clip_path
        })
        bld_clip = QgsVectorLayer(bld_clip_path, "bld_clip", "ogr")
        proj.addMapLayer(bld_clip)
    else:
        print("⚠ 建物データが見つかりません。スキップします。")

    # ---- 3. 橋データの処理 (再投影 -> クリップのみ) ----
    # ※ Phase 2 で使うため、ラスタライズは不要だがクリップデータが必要
    brid_src = get_or_load_layer("brid_2d", brid_path)
    brid_clip_path = os.path.join(output_dir, "brid_clip.gpkg")

    if brid_src:
        print(f"\n▶ 橋データ処理中: {brid_src.name()}")
        
        # 再投影
        brid_6677_path = os.path.join(output_dir, "brid_6677.gpkg")
        print("  [*] 橋を再投影中...")
        processing.run("native:reprojectlayer", {
            "INPUT": brid_src, "TARGET_CRS": "EPSG:6677", "OUTPUT": brid_6677_path
        })
        brid_6677 = QgsVectorLayer(brid_6677_path, "brid_6677", "ogr")
        
        # クリップ
        print("  [*] 橋をAOIでクリップ中...")
        processing.run("native:clip", {
            "INPUT": brid_6677, "OVERLAY": aoi, "OUTPUT": brid_clip_path
        })
        brid_clip = QgsVectorLayer(brid_clip_path, "brid_clip", "ogr")
        proj.addMapLayer(brid_clip)
        print(f"  ✔ 保存完了: {brid_clip_path}")
    else:
        print(f"\n⚠ 橋データが見つかりません: {brid_path}")
        print("  → Phase 2 の高架下判定はスキップされます (Risk=0)")

    # ---- 4. 建物のラスタライズ (今まで通り) ----
    if bld_src:
        extent = aoi.extent()
        width_m = extent.width()
        height_m = extent.height()
        extent_str = f"{extent.xMinimum()},{extent.xMaximum()},{extent.yMinimum()},{extent.yMaximum()} [EPSG:6677]"
        
        def rasterize_height(out_path, pixel_size, name):
            cols = int(math.ceil(width_m / pixel_size))
            rows = int(math.ceil(height_m / pixel_size))
            print(f"\n[*] {pixel_size:.1f}m ラスタ {name} を作成中...")
            params = {
                "INPUT": bld_clip_path, "FIELD": "measuredHeight", "BURN": 0, "UNITS": 1,
                "WIDTH": cols, "HEIGHT": rows, "EXTENT": extent_str, "NODATA": 0,
                "DATA_TYPE": 5, "INIT": 0, "OUTPUT": out_path
            }
            processing.run("gdal:rasterize", params)

        bld_3m_path = os.path.join(output_dir, "bld_height_3m.tif")
        bld_5m_path = os.path.join(output_dir, "bld_height_5m.tif")
        rasterize_height(bld_3m_path, 3.0, "bld_height_3m")
        rasterize_height(bld_5m_path, 5.0, "bld_height_5m")
        
        # プロジェクトに追加
        for p, n in [(bld_3m_path, "bld_height_3m"), (bld_5m_path, "bld_height_5m")]:
            lyr = QgsRasterLayer(p, n)
            if lyr.isValid(): proj.addMapLayer(lyr)

    print("\n=========== DATA PREPROCESSING DONE ===========")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    processed_data_dir = os.path.join(base_dir, "..", "data", "processed")
    raw_data_dir = os.path.join(base_dir, "..", "data", "raw")
    
    # ファイル名設定
    aoi_file = os.path.join(raw_data_dir, "aoi.geojson")
    bld_file = os.path.join(raw_data_dir, "plateau_bld.gpkg")
    
    # ★ ここ重要: 橋のデータファイル名を指定 (もし名前が違うならここを変える)
    brid_file = os.path.join(raw_data_dir, "plateau_brid.gpkg") 
    
    run_rasterization(
        output_dir=processed_data_dir,
        bld_path=bld_file,
        brid_path=brid_file,
        aoi_path=aoi_file
    )
