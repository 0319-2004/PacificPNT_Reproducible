import os

def calculate_area_statistics(output_dir, counts, pixel_size=5):
    """
    指定されたピクセル数(counts)と解像度(pixel_size)に基づいて
    面積と構成比率を計算し、コンソールに出力する。
    """
    print("=========== AREA SUMMARY START ===========")

    # 出力先フォルダの自動生成（このスクリプトではファイル出力はないが、統一ルールとして維持）
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"[*] ディレクトリを作成しました: {output_dir}")

    area_per_pix = pixel_size * pixel_size  # m^2
    total = sum(counts.values())

    print(f"▶ 基準ディレクトリ: {output_dir}")
    print("pixel_size(m):", pixel_size)
    print("valid_pixels:", total)
    print("valid_area_m2:", total * area_per_pix)

    labels = {1: "open", 2: "street", 3: "alley"}
    
    print("\n--- Classification Result ---")
    for k in sorted(counts):
        # ラベルが存在しない場合のフォールバック（念のため）
        label = labels.get(k, f"class_{k}")
        
        a = counts[k] * area_per_pix
        if total > 0:
            p = counts[k] / total * 100
        else:
            p = 0.0
            
        print(f"{k} {label}: pixels={counts[k]} area_m2={a} share={p:.2f}%")

    print("=========== AREA SUMMARY DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: qgis_scripts/ (Rootから1階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # data/processed へのパス (../data/processed)
    processed_dir = os.path.join(base_dir, "..", "data", "processed")
    
    # 解析対象のピクセル数（直前の解析結果などをここに定義）
    # 5m解像度の class raster の面積サマリ
    input_counts = {1: 2888, 2: 3850, 3: 2888}
    
    # 関数実行
    calculate_area_statistics(
        output_dir=processed_dir,
        counts=input_counts,
        pixel_size=5
    )
