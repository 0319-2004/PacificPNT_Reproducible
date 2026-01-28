import os
import math
import processing
from qgis.core import QgsProject, QgsRasterLayer

def classify_risk_based_on_quantiles(output_dir, input_raster_path):
    """
    指定されたリスク指標ラスタ(risk_proxy)の分位点(30%, 70%)を計算し、
    3段階のリスククラスに分類したラスタを出力する。
    """
    print("=========== RISK CLASSIFICATION START ===========")

    # 出力先フォルダの自動生成
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"[*] ディレクトリを作成しました: {output_dir}")

    # 出力ファイルパス
    out_path = os.path.join(output_dir, "risk_class_5m_py.tif")

    # ==== 1. 入力ラスタの読み込み (パス指定で再現性確保) ====
    if not os.path.exists(input_raster_path):
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_raster_path}")

    layer_name = os.path.basename(input_raster_path)
    risk_layer = QgsRasterLayer(input_raster_path, layer_name)

    if not risk_layer.isValid():
        raise RuntimeError(f"入力ラスタのロードに失敗しました: {input_raster_path}")

    print("▶ INPUT:", input_raster_path)
    print("▶ CRS:", risk_layer.crs().authid())
    print("▶ Size:", risk_layer.width(), "x", risk_layer.height())

    # ==== 2. 値を全て読み取り、ECDF（分位点）を計算 ====
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
        raise RuntimeError("有効ピクセルが0です（入力がNoDataのみの可能性）。AOIマスク/入力レイヤを確認してください。")

    # 分位点計算ロジック (既存維持)
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

    # ==== 3. 分類式（Raster Calculator） ====
    # クラス1: < q30 (低リスク)
    # クラス2: >= q30 AND < q70 (中リスク)
    # クラス3: >= q70 (高リスク)
    expr = f"(A < {q30})*1 + ((A >= {q30})*(A < {q70}))*2 + (A >= {q70})*3"
    print("▶ Expression:", expr)

    params = {
        "INPUT_A": input_raster_path,
        "BAND_A": 1,
        "INPUT_B": None, "BAND_B": -1,
        "INPUT_C": None, "BAND_C": -1,
        "INPUT_D": None, "BAND_D": -1,
        "INPUT_E": None, "BAND_E": -1,
        "INPUT_F": None, "BAND_F": -1,
        "FORMULA": expr,
        "NO_DATA": 0,
        "RTYPE": 5,    # Float32
        "EXTRA": "",
        "OUTPUT": out_path
    }

    print("[*] running gdal:rastercalculator ...")
    processing.run("gdal:rastercalculator", params)

    print("[+] created:", out_path)
    
    # ==== 4. 結果レイヤの追加 ====
    out_lyr = QgsRasterLayer(out_path, "risk_class_5m_py")
    if out_lyr.isValid():
        QgsProject.instance().addMapLayer(out_lyr)
        print("[+] added layer: risk_class_5m_py")
    else:
        print("⚠ 出力ラスタの読み込みに失敗しました")

    print("=========== RISK CLASSIFICATION DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: qgis_scripts/ (Rootから1階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # data/processed へのパス (../data/processed)
    processed_dir = os.path.join(base_dir, "..", "data", "processed")
    
    # 入力ファイルパス (前工程の出力と想定)
    input_tif = os.path.join(processed_dir, "risk_proxy_5m.tif")
    
    # 関数実行
    classify_risk_based_on_quantiles(processed_dir, input_tif)

