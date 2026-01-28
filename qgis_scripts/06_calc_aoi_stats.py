import os
import processing
import numpy as np
from qgis.core import (
    QgsVectorLayer,
    QgsRasterLayer,
    QgsProject,
    QgsProcessingFeatureSourceDefinition
)

def calculate_aoi_statistics(base_dir, raster_filename="risk_class_5m_py.tif", aoi_layer_name="aoi"):
    """
    分類済みラスタ(risk_class)を読み込み、各クラスの面積を集計する。
    さらにAOI(EPSG:6677)の総面積と比較し、カバー率を算出する。
    """
    print("=========== AOI STATISTICS CALCULATION START ===========")

    # パス設定
    # qgis_scripts/ から見て ../data/processed
    processed_dir = os.path.join(base_dir, "..", "data", "processed")
    raster_path = os.path.join(processed_dir, raster_filename)

    # 出力先確認（計算結果の保存などは任意だが、ディレクトリは確認）
    if not os.path.exists(processed_dir):
        raise FileNotFoundError(f"ディレクトリが見つかりません: {processed_dir}")

    # ----------------------------------------------------
    # 1. AOIレイヤの取得と面積計算 (EPSG:6677)
    # ----------------------------------------------------
    proj = QgsProject.instance()
    aoi_layers = proj.mapLayersByName(aoi_layer_name)
    
    if not aoi_layers:
        raise RuntimeError(f"AOIレイヤ '{aoi_layer_name}' がQGISプロジェクト内で見つかりません。")
    
    aoi_src = aoi_layers[0]
    
    # 面積計算用に一時的に投影変換 (EPSG:6677)
    print(f"[*] AOI面積を計算中 (Source CRS: {aoi_src.crs().authid()})...")
    params_reproj = {
        "INPUT": aoi_src,
        "TARGET_CRS": "EPSG:6677",
        "OPERATION": "",
        "OUTPUT": "TEMPORARY_OUTPUT"
    }
    result = processing.run("native:reprojectlayer", params_reproj)
    aoi_reproj = result["OUTPUT"]
    
    # 全フィーチャの面積合計を算出
    total_aoi_area_m2 = 0.0
    for feature in aoi_reproj.getFeatures():
        if feature.hasGeometry():
            total_aoi_area_m2 += feature.geometry().area()
            
    print(f"▶ AOI 総面積: {total_aoi_area_m2:,.2f} m²")

    # ----------------------------------------------------
    # 2. ラスタデータの読み込みと集計
    # ----------------------------------------------------
    if not os.path.exists(raster_path):
        raise FileNotFoundError(f"集計対象のラスタが見つかりません: {raster_path}")

    print(f"[*] ラスタを集計中: {raster_path}")
    raster_layer = QgsRasterLayer(raster_path, "target_raster")
    
    if not raster_layer.isValid():
        raise RuntimeError("ラスタの読み込みに失敗しました。")

    # ピクセルサイズ取得 (m)
    pixel_size_x = raster_layer.rasterUnitsPerPixelX()
    pixel_size_y = raster_layer.rasterUnitsPerPixelY()
    area_per_pixel = pixel_size_x * pixel_size_y
    print(f"▶ ピクセルサイズ: {pixel_size_x:.2f}m x {pixel_size_y:.2f}m (1px = {area_per_pixel:.2f} m²)")

    # ラスタの値を取得してカウント
    provider = raster_layer.dataProvider()
    extent = raster_layer.extent()
    cols = raster_layer.width()
    rows = raster_layer.height()
    
    # ブロック全体を取得
    block = provider.block(1, extent, cols, rows)
    no_data_val = provider.sourceNoDataValue(1)
    
    # バイナリデータとして取得し、Numpy配列化して高速集計
    # ※ データ型に応じて読み方が変わるが、ここではFloat32/Int等を想定して汎用的に処理
    raw_data = []
    for r in range(rows):
        for c in range(cols):
            val = block.value(c, r)
            # NoData判定
            if no_data_val is not None and val == no_data_val:
                continue
            # NaN判定
            if isinstance(val, float) and np.isnan(val):
                continue
            # 0も無効値(背景)として扱う場合が多いので除外（必要に応じて変更可）
            if val == 0:
                continue
                
            raw_data.append(int(val)) # クラスIDなのでint化

    # 集計実行
    if not raw_data:
        print("⚠ 有効なピクセルが1つもありませんでした。")
        return

    unique_classes, counts = np.unique(raw_data, return_counts=True)
    stats = dict(zip(unique_classes, counts))
    
    total_valid_pixels = sum(counts)
    total_valid_area_m2 = total_valid_pixels * area_per_pixel

    # ----------------------------------------------------
    # 3. 結果の表示
    # ----------------------------------------------------
    labels = {1: "Open (Low Risk)", 2: "Street (Med Risk)", 3: "Alley (High Risk)"}
    
    print("\n" + "="*40)
    print(f"  Classification Statistics")
    print("="*40)
    
    for cls_id in sorted(stats.keys()):
        count = stats[cls_id]
        area_m2 = count * area_per_pixel
        
        # 構成比 (有効ピクセルに対する割合)
        share_pct = (count / total_valid_pixels) * 100
        
        # 対AOI比 (AOI全体に対するそのクラスの占有率)
        aoi_coverage_pct = (area_m2 / total_aoi_area_m2) * 100
        
        label_name = labels.get(cls_id, f"Class {cls_id}")
        
        print(f"[{label_name}]")
        print(f"  - Count   : {count:,} px")
        print(f"  - Area    : {area_m2:,.2f} m²")
        print(f"  - Share   : {share_pct:.2f}% (of valid area)")
        print(f"  - Density : {aoi_coverage_pct:.2f}% (of total AOI)")
        print("-" * 20)

    # 全体サマリ
    valid_coverage_pct = (total_valid_area_m2 / total_aoi_area_m2) * 100
    print(f"\n[Summary]")
    print(f"  Total Valid Area : {total_valid_area_m2:,.2f} m²")
    print(f"  AOI Coverage     : {valid_coverage_pct:.2f}% (建物等がAOIに占める割合)")
    
    print("=========== AOI STATISTICS CALCULATION DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: qgis_scripts/ (Rootから1階層深い)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 実行
    # ※ QGIS上で `aoi` レイヤが開かれている状態で実行してください
    calculate_aoi_statistics(
        base_dir=current_dir,
        raster_filename="risk_class_5m_py.tif", # 集計したいファイル名
        aoi_layer_name="aoi"
    )
