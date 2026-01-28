import os
import math
import processing
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer

def get_or_load_layer(layer_name, file_path, optional=False):
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
        if optional:
            print(f"⚠ 任意ファイルが見つかりません（スキップします）: {os.path.basename(file_path)}")
            return None
        else:
            raise FileNotFoundError(f"❌ 必須ファイルが見つかりません: {file_path}")
    
    print(f"📂 ファイルからロード中: {os.path.basename(file_path)}")
    layer = QgsVectorLayer(file_path, layer_name, "ogr")
    
    if not layer.isValid():
        if optional:
            return None
        raise RuntimeError(f"❌ レイヤのロードに失敗: {file_path}")
    
    proj.addMapLayer(layer)
    return layer

def run_preprocessing(output_dir, bld_path, brid_path, aoi_path):
    """
    Rawデータ(建物・橋)を読み込み、AOIでクリップ・再投影して保存する。
    """
    print("=========== DATA PREPROCESSING START ===========")
    
    os.makedirs(output_dir, exist_ok=True)
    proj = QgsProject.instance()

    # ---- 1. AOIの準備 (必須) ----
    aoi_origin = get_or_load_layer("aoi", aoi_path)
    print(f"▶ AOIレイヤ: {aoi_origin.name()} ({aoi_origin.crs().authid()})")

    # EPSG:6677 に変換
    print("\n[*] AOIレイヤを EPSG:6677 に再投影します...")
    result_aoi = processing.run("native:reprojectlayer", {
        "INPUT": aoi_origin, "TARGET_CRS": "EPSG:6677", "OUTPUT": "TEMPORARY_OUTPUT"
    })
    aoi_6677 = result_aoi['OUTPUT']
    aoi = aoi_6677 # 以降はこれを使用

    # ==========================================
    # 2. 建物データの処理 (必須)
    # Raw(bld) -> Reproject -> Clip -> Processed(bld_clip.gpkg) -> Raster(tif)
    # ==========================================
    bld_src = get_or_load_layer("bld_raw", bld_path)
    bld_clip_path = os.path.join(output_dir, "bld_clip.gpkg")

    if bld_src:
        # 再投影
        bld_6677_path = os.path.join(output_dir, "bld_6677.gpkg")
        print("\n[*] 建物を EPSG:6677 に再投影中...")
        processing.run("native:reprojectlayer", {
            "INPUT": bld_src, "TARGET_CRS": "EPSG:6677", "OUTPUT": bld_6677_path
        })
        bld_6677 = QgsVectorLayer(bld_6677_path, "bld_6677", "ogr")
        
        # クリップ
        print("[*] 建物をAOIでクリップ中...")
        processing.run("native:clip", {
            "INPUT": bld_6677, "OVERLAY": aoi, "OUTPUT": bld_clip_path
        })
        bld_clip = QgsVectorLayer(bld_clip_path, "bld_clip", "ogr")
        proj.addMapLayer(bld_clip)

        # ラスタライズ (3m / 5m)
        extent = aoi.extent()
        width_m = extent.width()
        height_m = extent.height()
        extent_str = f"{extent.xMinimum()},{extent.xMaximum()},{extent.yMinimum()},{extent.yMaximum()} [EPSG:6677]"
        
        def rasterize_height(out_path, pixel_size, name):
            cols = int(math.ceil(width_m / pixel_size))
            rows = int(math.ceil(height_m / pixel_size))
            print(f"[*] {pixel_size:.1f}m ラスタ {name} を作成中...")
            processing.run("gdal:rasterize", {
                "INPUT": bld_clip_path, "FIELD": "measuredHeight", "BURN": 0, "UNITS": 1,
                "WIDTH": cols, "HEIGHT": rows, "EXTENT": extent_str, "NODATA": 0,
                "DATA_TYPE": 5, "INIT": 0, "OUTPUT": out_path
            })

        rasterize_height(os.path.join(output_dir, "bld_height_3m.tif"), 3.0, "bld_height_3m")
        rasterize_height(os.path.join(output_dir, "bld_height_5m.tif"), 5.0, "bld_height_5m")

    # ==========================================
    # 3. 橋データの処理 (任意だがPhase 2で必須)
    # Raw(brid) -> Reproject -> Clip -> Processed(brid_clip.gpkg)
    # ==========================================
    brid_src = get_or_load_layer("brid_raw", brid_path, optional=True)
    
    if brid_src:
        brid_clip_path = os.path.join(output_dir, "brid_clip.gpkg")
        brid_6677_path = os.path.join(output_dir, "brid_6677.gpkg")
        
        print("\n[*] 橋データを EPSG:6677 に再投影中...")
        processing.run("native:reprojectlayer", {
            "INPUT": brid_src, "TARGET_CRS": "EPSG:6677", "OUTPUT": brid_6677_path
        })
        brid_6677 = QgsVectorLayer(brid_6677_path, "brid_6677", "ogr")
        
        print("[*] 橋データをAOIでクリップ中...")
        processing.run("native:clip", {
            "INPUT": brid_6677, "OVERLAY": aoi, "OUTPUT": brid_clip_path
        })
        # 結果をロード
        brid_clip = QgsVectorLayer(brid_clip_path, "brid_clip", "ogr")
        if brid_clip.isValid():
            proj.addMapLayer(brid_clip)
            print(f"✔ 橋データの処理完了: {brid_clip_path}")
    else:
        print("\n⚠ 橋データ(raw)が見つからないため、高架下の解析用データは生成されません。")
        print("   -> Phase 2 の解析を行う場合は data/raw/plateau_brid.gpkg を配置してください。")

    print("\n=========== DATA PREPROCESSING DONE ===========")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    processed_data_dir = os.path.join(base_dir, "..", "data", "processed")
    raw_data_dir = os.path.join(base_dir, "..", "data", "raw")
    
    # ユーザーが配置すべきRawファイル名
    aoi_file = os.path.join(raw_data_dir, "aoi.geojson")
    bld_file = os.path.join(raw_data_dir, "plateau_bld.gpkg")
    brid_file = os.path.join(raw_data_dir, "plateau_brid.gpkg") 
    
    run_preprocessing(
        output_dir=processed_data_dir,
        bld_path=bld_file,
        brid_path=brid_file,
        aoi_path=aoi_file
    )
