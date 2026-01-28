import os
import time
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField,
    QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant

def generate_empty_sites_layer(output_dir):
    """
    空の候補地(PNT sites)レイヤを作成し、GeoPackageとして保存・ロードする。
    既存の同名ファイルがある場合はロックを解除して上書きを試みる。
    """
    print("=========== PNT SITES LAYER GENERATION START ===========")

    # 出力先フォルダの自動生成
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"[*] ディレクトリを作成しました: {output_dir}")

    LAYER_NAME = "PNT_sites_raw"
    CRS_AUTHID = "EPSG:6677"
    gpkg_path = os.path.join(output_dir, "pnt_sites.gpkg")

    print(f"[INFO] output gpkg: {gpkg_path}")

    proj = QgsProject.instance()

    # 1) もし同じgpkgを参照しているレイヤがあれば全部外す（ロック回避）
    to_remove = []
    for lyr in proj.mapLayers().values():
        try:
            src = lyr.source()
        except:
            continue
        # パスが含まれているか判定
        if gpkg_path in src:
            to_remove.append(lyr.id())

    for lid in to_remove:
        proj.removeMapLayer(lid)

    if to_remove:
        print(f"[OK] removed {len(to_remove)} layer(s) that referenced the gpkg")

    # 2) 既存gpkgを削除（更新モードで開けない問題を回避）
    if os.path.exists(gpkg_path):
        try:
            os.remove(gpkg_path)
            print("[OK] deleted existing gpkg")
        except Exception as e:
            # 削除できないならタイムスタンプを付与して回避
            ts = time.strftime("%Y%m%d_%H%M%S")
            gpkg_path = os.path.join(output_dir, f"pnt_sites_{ts}.gpkg")
            print("[WARN] could not delete existing gpkg -> write to:", gpkg_path)

    # 3) 空のメモリ点レイヤを作成
    vl = QgsVectorLayer(f"Point?crs={CRS_AUTHID}", LAYER_NAME, "memory")
    if not vl.isValid():
        raise RuntimeError("Failed to create memory layer")

    prov = vl.dataProvider()
    prov.addAttributes([
        QgsField("site_id", QVariant.String),
        QgsField("risk_raw", QVariant.Double),
        QgsField("svf_raw", QVariant.Double),
        QgsField("risk_class_pre", QVariant.Int),
        QgsField("use", QVariant.Int),
        QgsField("note", QVariant.String),
    ])
    vl.updateFields()

    # 4) 新規ファイルとして書き出す（更新ではなく“新規作成”）
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = LAYER_NAME

    # 環境差を吸収：CreateOrOverwriteFile があれば使う
    if hasattr(QgsVectorFileWriter, "CreateOrOverwriteFile"):
        opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

    ret = QgsVectorFileWriter.writeAsVectorFormatV3(vl, gpkg_path, proj.transformContext(), opts)

    # ret の形が環境で違うので吸収
    err_code = ret[0] if isinstance(ret, tuple) and len(ret) >= 1 else ret
    err_msg  = ret[1] if isinstance(ret, tuple) and len(ret) >= 2 else ""

    if err_code != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Write failed: code={err_code}, msg={err_msg}")

    print("[OK] wrote gpkg")

    # 5) 書き出したレイヤを読み込んでプロジェクトに追加
    uri = f"{gpkg_path}|layername={LAYER_NAME}"
    gpkg_layer = QgsVectorLayer(uri, LAYER_NAME, "ogr")
    if not gpkg_layer.isValid():
        raise RuntimeError("Failed to load gpkg layer (ogr). Check path/permission.")

    proj.addMapLayer(gpkg_layer)
    print("[✓] Added layer to project:", gpkg_layer.name())

    print("=========== PNT SITES LAYER GENERATION DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: qgis_scripts/ (Rootから1階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # data/processed へのパス (../data/processed)
    processed_dir = os.path.join(base_dir, "..", "data", "processed")
    
    # 関数実行
    generate_empty_sites_layer(processed_dir)
