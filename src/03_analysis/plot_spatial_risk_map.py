import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import geopandas as gpd  # 追加

def plot_risk_map_with_labels(data, value_col, title, filename, output_dir, a11_data=None, aoi_gdf=None):
    """
    指定されたリスク値を地図上にプロットし、背景にAOIを描画する
    """
    if value_col not in data.columns:
        print(f"[Skip] Column '{value_col}' not found in dataset.")
        return

    save_path = os.path.join(output_dir, filename)
    
    plt.figure(figsize=(12, 12))
    plt.style.use('default')
    
    # --- 追加: 背景のAOI描画 ---
    if aoi_gdf is not None:
        aoi_gdf.plot(
            ax=plt.gca(),
            facecolor='none',
            edgecolor='gray',
            linestyle='--',
            linewidth=1.5,
            zorder=1,
            label='AOI Boundary'
        )
    
    # メインの散布図 (zorderを2に設定)
    sc = plt.scatter(data['center_x_6677'], data['center_y_6677'], 
                     c=data[value_col], cmap='coolwarm', 
                     s=150, edgecolors='black', vmin=0, vmax=1.0, zorder=2)
    
    # A11の強調 (zorderを3に設定)
    if a11_data is not None:
        plt.scatter(a11_data['center_x_6677'], a11_data['center_y_6677'], 
                    s=500, facecolors='none', edgecolors='#00FF00', linewidth=3, 
                    label='Site A11 (Underpass)', zorder=3)
    
    # 全地点のラベル付け (zorderを4に設定)
    for i, row in data.iterrows():
        label = str(row['site_id'])
        x = row['center_x_6677']
        y = row['center_y_6677']
        
        if label == 'A11':
            plt.text(x + 15, y + 15, label, fontsize=12, fontweight='bold', color='green', zorder=4)
        else:
            plt.text(x + 10, y + 10, label, fontsize=9, color='black', alpha=0.8, zorder=4)

    plt.colorbar(sc, label='Risk Score (0=Safe, 1=Danger)', shrink=0.8)
    plt.title(title, fontsize=16, fontweight='bold')
    plt.xlabel('X Coordinate (JGD2011 / Plane Rectangular VII) [m]')
    plt.ylabel('Y Coordinate (JGD2011 / Plane Rectangular VII) [m]')
    plt.grid(True, linestyle='--', alpha=0.5, zorder=0)
    plt.axis('equal')
    plt.legend(loc='upper right', fontsize=12)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"Saved plot to: {save_path}")


def generate_spatial_risk_maps(input_csv_path, aoi_geojson_path, output_dir):
    """
    AOIを読み込み、各種リスクマップを生成するメイン処理
    """
    print("=========== SPATIAL RISK MAPPING START ===========")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # 1. データの読み込み
    if not os.path.exists(input_csv_path):
        raise FileNotFoundError(f"Input file not found: {input_csv_path}")
    df = pd.read_csv(input_csv_path)

    # 2. AOIの読み込みと変換 (EPSG:4326 -> EPSG:6677)
    aoi_gdf = None
    if os.path.exists(aoi_geojson_path):
        print(f"Loading AOI from: {aoi_geojson_path}")
        aoi_gdf = gpd.read_file(aoi_geojson_path)
        aoi_gdf = aoi_gdf.to_crs(epsg=6677)
    else:
        print(f"[Warning] AOI file not found: {aoi_geojson_path}")

    # A11の位置特定
    a11 = None
    if 'site_id' in df.columns:
        df['site_id'] = df['site_id'].astype(str)
        a11_rows = df[df['site_id'] == 'A11']
        if not a11_rows.empty:
            a11 = a11_rows.iloc[0]
    
    # --- 各マップの生成 ---
    
    # (a) Initial Risk Map
    plot_risk_map_with_labels(
        df, 'risk_proxy_5m', 
        '(a) Initial Risk Map (Site Selection Phase)', 
        'figure3_a_initial_labeled.png',
        output_dir, a11, aoi_gdf
    )

    # (b) Phase 1 Result
    plot_risk_map_with_labels(
        df, 'risk_horizon', 
        '(b) Phase 1 Prediction (Building-Only Model)', 
        'figure3_b_phase1_labeled.png',
        output_dir, a11, aoi_gdf
    )

    # (c) Phase 2 Result
    if 'overhead_flag' in df.columns and 'risk_horizon' in df.columns:
        df['risk_hybrid'] = df.apply(lambda x: 1.0 if x['overhead_flag'] == 1 else x['risk_horizon'], axis=1)
        plot_risk_map_with_labels(
            df, 'risk_hybrid', 
            '(c) Phase 2 Prediction (Infrastructure Integrated)', 
            'figure3_c_phase2_labeled.png',
            output_dir, a11, aoi_gdf
        )

    print("=========== SPATIAL RISK MAPPING DONE ===========")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # パス設定
    input_data_path = os.path.join(base_dir, "..", "..", "data", "processed", "final_dataset.csv")
    aoi_path = os.path.join(base_dir, "..", "..", "data", "raw", "aoi.geojson")
    output_figures_dir = os.path.join(base_dir, "..", "..", "output", "figures")

    try:
        generate_spatial_risk_maps(input_data_path, aoi_path, output_figures_dir)
    except Exception as e:
        print(f"Error: {e}")
