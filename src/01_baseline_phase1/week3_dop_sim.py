import os
import glob
import math
import csv
import numpy as np
import pandas as pd
from pathlib import Path

# ==========================================
# 計算エンジン (DOP Simulator Logic)
# ==========================================
def calculate_hdop(satellites):
    """
    衛星の配置(Azimuth, Elevation)から、幾何学的精度低下率(HDOP)を計算する。
    HDOPが小さいほど、衛星配置が良い（精度が出やすい）。
    """
    if len(satellites) < 4:
        return np.nan  # 衛星が4機未満なら測位不能

    G = []
    for az_deg, el_deg in satellites:
        # 角度をラジアンに変換
        az = math.radians(az_deg)
        el = math.radians(el_deg)
        
        # 視線ベクトル (East, North, Up)
        # Azimuthは北基準時計回り前提
        x = math.cos(el) * math.sin(az)
        y = math.cos(el) * math.cos(az)
        z = math.sin(el)
        
        # 時刻誤差項(1)を含めた行列
        G.append([x, y, z, 1])
    
    G = np.array(G)
    
    try:
        # (G^T * G) の逆行列を計算
        Q = np.linalg.inv(G.T @ G)
        # HDOP = sqrt(Q_east + Q_north) = sqrt(Q[0,0] + Q[1,1])
        hdop = math.sqrt(Q[0, 0] + Q[1, 1])
        return hdop
    except np.linalg.LinAlgError:
        return np.nan # 特異行列などで計算不能

def parse_and_simulate(filepath):
    """
    1つのログファイルを読み込み、Cut-A(5度)とCut-B(15度)のHDOPを計算する
    """
    # データを格納する辞書: time -> list of (az, el)
    epochs = {}
    
    # pathlib.Pathオブジェクトか確認して文字列化（openで使うため）あるいはPathのままopen
    path_obj = Path(filepath)
    print(f"Processing: {path_obj.name} ...")
    
    with path_obj.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        header_map = {}
        
        for row in reader:
            if not row: continue
            
            # ヘッダー行の解析 (# Status, UnixTimeMillis, ...)
            if row[0].startswith("#") and "Status" in row[0]:
                clean_row = [c.strip().replace("#", "").strip() for c in row]
                try:
                    type_idx = clean_row.index("Status")
                    for i, col in enumerate(clean_row[type_idx+1:]):
                        header_map[col] = type_idx + 1 + i
                except ValueError:
                    pass
                continue

            # データ行の解析
            if row[0].strip() == "Status":
                try:
                    idx_time = header_map.get("UnixTimeMillis")
                    idx_el = header_map.get("ElevationDegrees")
                    idx_az = header_map.get("AzimuthDegrees")
                    
                    if idx_time is None or idx_el is None or idx_az is None:
                        continue
                        
                    t = row[idx_time]
                    el = float(row[idx_el])
                    az = float(row[idx_az])
                    
                    if t not in epochs:
                        epochs[t] = []
                    epochs[t].append((az, el))
                except (ValueError, IndexError):
                    continue

    # --- シミュレーション実行 ---
    stats_a = []
    stats_b = []
    
    for t, sats in epochs.items():
        # Cut-A: 5度以上
        sats_a = [(az, el) for (az, el) in sats if el >= 5.0]
        hdop_a = calculate_hdop(sats_a)
        
        # Cut-B: 15度以上
        sats_b = [(az, el) for (az, el) in sats if el >= 15.0]
        hdop_b = calculate_hdop(sats_b)
        
        if not np.isnan(hdop_a): stats_a.append(hdop_a)
        if not np.isnan(hdop_b): stats_b.append(hdop_b)

    return {
        "site_id": path_obj.stem.split("_")[0],
        "hdop_cut_a_median": np.nanmedian(stats_a) if stats_a else np.nan,
        "hdop_cut_b_median": np.nanmedian(stats_b) if stats_b else np.nan,
        "valid_epochs": len(epochs)
    }

# ==========================================
# メイン処理関数 (モジュール化)
# ==========================================
def run_dop_simulation(input_dir, output_csv_path):
    print("=========== DOP SIMULATION START ===========")
    
    # 出力先ディレクトリの自動生成
    out_dir = os.path.dirname(output_csv_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
        print(f"[*] ディレクトリを作成しました: {out_dir}")

    # 入力ファイルの検索
    log_files = glob.glob(os.path.join(input_dir, "*.txt"))
    if not log_files:
        print(f"エラー: {input_dir} に .txt ファイルが見つかりません。")
        return

    print(f"Found {len(log_files)} logs in {input_dir}")

    results = []
    for log_file in log_files:
        res = parse_and_simulate(log_file)
        results.append(res)
    
    df = pd.DataFrame(results)
    df.to_csv(output_csv_path, index=False)
    
    print("-" * 30)
    print(f"完了！結果を {output_csv_path} に保存しました。")
    print("=========== DOP SIMULATION DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: src/01_baseline_phase1/ (Rootから2階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 入力ディレクトリ: ../../data/processed/gnss_normalized (整形済みログを推奨)
    input_log_dir = os.path.join(base_dir, "..", "..", "data", "processed", "gnss_normalized")
    
    # 出力ファイル: ../../output/baseline_analysis/week3_dop_results.csv
    output_csv = os.path.join(base_dir, "..", "..", "output", "baseline_analysis", "week3_dop_results.csv")
    
    # 実行
    run_dop_simulation(input_log_dir, output_csv)
