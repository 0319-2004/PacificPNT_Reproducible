import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Point
import math
import os

# ==========================================
# 設定
# ==========================================
INPUT_BLDG_FILE = "data/bldg_aoi.gpkg"
INPUT_BRID_FILE = "data/brid_aoi.gpkg"
INPUT_SITES_CSV = "site_centers.csv"

OUTPUT_DIR = "week3_analysis2"
OUTPUT_FILENAME = "sites_risk.csv"

# 計算パラメータ
SEARCH_RADIUS_M = 50.0
CALC_HEIGHT_M = 1.5
CRS_METRIC = "EPSG:6677"
DEFAULT_HEIGHT = 15.0

# 【重要】A11（高架下）を拾うためのバッファサイズ
# 座標が微妙にズレていても、2.0m広げれば確実に接触判定できる
OVERHEAD_BUFFER_M = 2.0 

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
    hit = brid_gdf.intersects(pbuf).any()
    
    if hit: return 1, 1.0
    return 0, 0.0

def main():
    print(f"--- Phase 2: Risk Calculation (Bldg + Bridge) ---")
    
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    # データ読み込み
    sites_df = pd.read_csv(INPUT_SITES_CSV)
    geometry = [Point(xy) for xy in zip(sites_df['center_x_6677'], sites_df['center_y_6677'])]
    sites_gdf = gpd.GeoDataFrame(sites_df, geometry=geometry, crs=CRS_METRIC)
    
    bldg_gdf = gpd.read_file(INPUT_BLDG_FILE).to_crs(CRS_METRIC)
    brid_gdf = gpd.read_file(INPUT_BRID_FILE).to_crs(CRS_METRIC)
    
    # 従来互換用の全結合データ
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

        # A11のデバッグ表示
        if site['site_id'] == 'A11':
            status = "SUCCESS" if oflag == 1 else "FAIL"
            print(f"  [CHECK A11] Overhead Flag: {oflag} ({status}) | Horizon: {risk_h:.3f}")

        results.append({
            'site_id': site['site_id'],
            'class': site['class'],
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
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
    out_df.to_csv(output_path, index=False)
    print(f"Saved to: {output_path}")

if __name__ == "__main__":
    main()
