import os
import math
from qgis.core import QgsRasterLayer

def analyze_raster_quantiles(input_raster_path):
    """
    指定されたラスタファイルのピクセル値を読み込み、分位点（30%, 50%, 70%）を計算して表示する。
    """
    print("=========== QUANTILE ANALYSIS START ===========")

    # --------- 1. 入力ファイルの確認とロード ---------
    if not os.path.exists(input_raster_path):
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_raster_path}")

    layer_name = os.path.basename(input_raster_path)
    layer = QgsRasterLayer(input_raster_path, layer_name)

    if not layer.isValid():
        raise RuntimeError(f"ラスタレイヤのロードに失敗しました: {input_raster_path}")

    print(f"▶ 対象レイヤ: {layer_name}")

    # --------- 2. データプロバイダから値を取得 ---------
    provider = layer.dataProvider()
    
    # ラスタブロックの取得
    block = provider.block(1, layer.extent(), layer.width(), layer.height())
    nodata = provider.sourceNoDataValue(1)

    values = []
    # 行・列のループで画素値を取得
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

    if not values:
        raise RuntimeError("値が1つも取れませんでした。有効なデータがあるか確認してください。")

    # --------- 3. 分位点計算ロジック (既存維持) ---------
    values.sort()
    n = len(values)

    def quantile(p):
        # 0〜1 の p に対する補間付き分位点
        if p <= 0:
            return values[0]
        if p >= 1:
            return values[-1]
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return values[int(k)]
        return values[f] + (values[c] - values[f]) * (k - f)

    print("n:", n)
    print("min:", values[0], "max:", values[-1])
    
    for p in (0.30, 0.50, 0.70):
        print(f"q{int(p*100)}:", quantile(p))

    print("=========== QUANTILE ANALYSIS DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: qgis_scripts/ (Rootから1階層深いと想定)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # data/processed へのパス (../data/processed)
    processed_dir = os.path.join(base_dir, "..", "data", "processed")
    
    # フォルダが存在しない場合は作成（読み込み専用処理だがルールに基づき記載）
    if not os.path.exists(processed_dir):
        os.makedirs(processed_dir, exist_ok=True)

    # 入力ファイル: 前工程で作成された risk_proxy_5m.tif を指定
    target_raster_path = os.path.join(processed_dir, "risk_proxy_5m.tif")
    
    # 関数実行
    analyze_raster_quantiles(target_raster_path)
