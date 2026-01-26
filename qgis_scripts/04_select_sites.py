exec(r"""
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField,
    QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant
import os, time

LAYER_NAME = "PNT_sites_raw"
CRS_AUTHID = "EPSG:6677"

# macでDesktop権限で詰まりやすいのでDocuments推奨
out_dir = os.path.join(os.path.expanduser("~"), "Documents")
gpkg_path = os.path.join(out_dir, "pnt_sites.gpkg")
print(f"[INFO] output gpkg: {gpkg_path}")

proj = QgsProject.instance()

# 1) もし同じgpkgを参照しているレイヤがあれば全部外す（ロック回避）
to_remove = []
for lyr in proj.mapLayers().values():
    try:
        src = lyr.source()
    except:
        continue
    if gpkg_path in src:
        to_remove.append(lyr.id())

for lid in to_remove:
    proj.removeMapLayer(lid)

print(f"[OK] removed {len(to_remove)} layer(s) that referenced the gpkg (if any)")

# 2) 既存gpkgを削除（更新モードで開けない問題を回避）
if os.path.exists(gpkg_path):
    try:
        os.remove(gpkg_path)
        print("[OK] deleted existing gpkg")
    except Exception as e:
        # 削除できないならファイル名を変えて作る
        ts = time.strftime("%Y%m%d_%H%M%S")
        gpkg_path = os.path.join(out_dir, f"pnt_sites_{ts}.gpkg")
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
""")
