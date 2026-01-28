import os
import math
import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point

# ==========================================
# 定数・設定
# ==========================================
# 計算パラメータ
SEARCH_RADIUS_M = 50.0
CALC_HEIGHT_M = 1.5
CRS_METRIC = "EPSG:6677"
DEFAULT_HEIGHT = 15.0

# 【重要】A11（高架下）を拾うためのバッファサイズ
OVERHEAD_BUFFER_M = 2.0

# ==========================================
# ヘルパー関数群
# ==========================================
def _pick_height_col(gdf):
    possible_cols = ["measuredHeight", "bldg_measuredHeight", "height", "z"]
    for c in possible_cols:
        if c in gdf.columns:
            return c
    return None

def risk_max_score(point, obstacles_gdf, radius_m, dist_scale_m=10.0):
    """MAX方式: 最も影響度の高い障害物のスコアを採用"""
    buf = point.buffer(radius_m)
    # 空間インデックスが利用可能な場合は活用（パフォーマンス向上）
    if obstacles_gdf.sindex:
        possible_matches_index = list(obstacles_gdf.sindex.intersection(buf.bounds))
        possible_matches = obstacles_gdf.iloc[possible_matches_index]
        nearby = possible_matches[possible_matches.intersects(buf)].copy()
    else:
        nearby = obstacles_gdf[obstacles_gdf.intersects(buf)].copy()

    if len(nearby) == 0:
        return 0.0

    height_col = _pick_height_col(nearby)
    max_score = 0.0
    
    for _, row in nearby.iterrows():
        dist = row.geometry.distance(point)
        if dist < 0.1: dist = 0.1

        h = DEFAULT_HEIGHT
        if height_col and pd.notna(row[height_col]):
            try: h = float(row[height_col])
            except: pass

        rel_h = h - CALC_HEIGHT_M
        if rel_h <= 0: continue

        elev_angle = math.degrees(math.atan2(rel_h, dist))
        angle_score = elev_angle / 90.0
        dist_score = 1.0 / (1.0 + dist / dist_scale_m)
        
        obj_score = angle_score * dist_score
        if obj_score > max_score:
            max_score = obj_score

    return float(min(max(max_score, 0.0), 1.0))

def overhead_score_binary(point, brid_gdf, buffer_m):
    """高架直下判定 (バッファ付き)"""
    if brid_gdf is None or len(brid_gdf) == 0:
        return 0, 0.0
    
    # 点の周りにバッファを張って接触判定（A11救済策）
    pbuf = point.buffer(buffer_m)
    
    if brid_gdf.sindex:
        possible_matches_index = list(brid_gdf.sindex.intersection(pbuf.bounds))
        possible_matches = brid_gdf.iloc[possible_matches_index]
        hit = possible_matches.intersects(pbuf).any()
    else:
        hit = brid_gdf.intersects(pbuf).any()
    
    if hit: return 1, 1.0
    return 0, 0.0

# ==========================================
# メイン処理関数
# ==========================================
def calculate_phase2_risk(
    input_bldg_path, 
    input_brid_path, 
    input_sites_csv, 
    output_dir, 
    output_filename="sites_risk.csv"
):
    print(f"--- Phase 2: Risk Calculation (Bldg + Bridge) ---")
    
    # 出力ディレクトリ作成
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"[*] ディレクトリを作成しました: {output_dir}")
    
    # ファイル存在確認
    for p in [input_bldg_path, input_brid_path, input_sites_csv]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"入力ファイルが見つかりません: {p}")

    # 1. 候補地データの読み込みとGeoDataFrame化
    sites_df = pd.read_csv(input_sites_csv)
    # site_definitions.csv (raw) を使用する場合も、ここで投影座標系 (EPSG:6677) のカラムが必要
    if 'center_x_6677' not in sites_df.columns or 'center_y_6677' not in sites_df.columns:
         raise ValueError(f"入力CSVに座標カラム(center_x_6677, center_y_6677)が含まれていません: {input_sites_csv}")

    geometry = [Point(xy) for xy in zip(sites_df['center_x_6677'], sites_df['center_y_6677'])]
    sites_gdf = gpd.GeoDataFrame(sites_df, geometry=geometry, crs=CRS_METRIC)
    
    # 2. 障害物データの読み込み
    bldg_gdf = gpd.read_file(input_bldg_path).to_crs(CRS_METRIC)
    brid_gdf = gpd.read_file(input_brid_path).to_crs(CRS_METRIC)
    
    # 従来互換用の全結合データ (risk_proxy_5m 相当の計算用)
    all_obstacles = pd.concat([bldg_gdf, brid_gdf], ignore_index=True)

    print(f"Sites: {len(sites_gdf)}, Bldgs: {len(bldg_gdf)}, Bridges: {len(brid_gdf)}")
    print(f"Calculating with Overhead Buffer = {OVERHEAD_BUFFER_M}m ...")

    results = []
    
    for idx, site in sites_gdf.iterrows():
        # 1. 従来の全部入り (risk_proxy_5m)
        risk_all = risk_max_score(site.geometry, all_obstacles, SEARCH_RADIUS_M)
        
        # 2. Risk Horizon (建物のみ)
        risk_h = risk_max_score(site.geometry, bldg_gdf, SEARCH_RADIUS_M)
        
        # 3. Overhead Score (橋のみ、バッファあり)
        oflag, oscore = overhead_score_binary(site.geometry, brid_gdf, buffer_m=OVERHEAD_BUFFER_M)

        # A11のデバッグ表示 (既存ロジック維持)
        if str(site['site_id']) == 'A11':
            status = "SUCCESS" if oflag == 1 else "FAIL"
            print(f"  [CHECK A11] Overhead Flag: {oflag} ({status}) | Horizon: {risk_h:.3f}")

        results.append({
            'site_id': site['site_id'],
            'class': site['class'] if 'class' in site else 0, # カラムが無い場合の安全策
            'center_x_6677': site['center_x_6677'],
            'center_y_6677': site['center_y_6677'],
            'risk_proxy_5m': risk_all,
            'svf_proxy_5m': 1.0 - risk_all,
            'risk_horizon': risk_h,
            'overhead_flag': oflag,
            'overhead_score': oscore
        })

    # 保存
    out_df = pd.DataFrame(results)
    output_path = os.path.join(output_dir, output_filename)
    out_df.to_csv(output_path, index=False)
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    # ファイル配置場所: src/02_proposed_phase2/ (Rootから2階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # パス設定
    processed_dir = os.path.join(base_dir, "..", "..", "data", "processed")
    raw_dir = os.path.join(base_dir, "..", "..", "data", "raw")
    
    # 入力ファイルパス
    in_bldg = os.path.join(processed_dir, "bldg_aoi.gpkg")
    in_brid = os.path.join(processed_dir, "brid_aoi.gpkg")
    
    # サイト定義データの統一: site_centers.csv -> site_definitions.csv (raw)
    in_sites = os.path.join(raw_dir, "site_definitions.csv")
    
    # 出力設定: ../../output/phase2_risk
    output_dir = os.path.join(base_dir, "..", "..", "output", "phase2_risk")
    
    # 実行
    try:
        calculate_phase2_risk(
            input_bldg_path=in_bldg,
            input_brid_path=in_brid,
            input_sites_csv=in_sites,
            output_dir=output_dir
        )
    except Exception as e:
        print(f"Error: {e}")
        print("※入力ファイルが存在しない場合は、パスやファイル名を確認してください。")
