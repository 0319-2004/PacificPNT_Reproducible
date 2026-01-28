import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def plot_risk_map_with_labels(data, value_col, title, filename, output_dir, a11_data=None):
    """
    指定されたリスク値を地図上にプロットし、保存するヘルパー関数
    """
    if value_col not in data.columns:
        print(f"[Skip] Column '{value_col}' not found in dataset.")
        return

    save_path = os.path.join(output_dir, filename)
    
    plt.figure(figsize=(12, 12))  # ラベルが見やすいようにサイズアップ
    plt.style.use('default')
    
    # メインの散布図 (青->赤)
    sc = plt.scatter(data['center_x_6677'], data['center_y_6677'], 
                     c=data[value_col], cmap='coolwarm', 
                     s=150, edgecolors='black', vmin=0, vmax=1.0, zorder=2)
    
    # A11の強調 (緑の丸) - 存在する場合のみ
    if a11_data is not None:
        plt.scatter(a11_data['center_x_6677'], a11_data['center_y_6677'], 
                    s=500, facecolors='none', edgecolors='#00FF00', linewidth=3, 
                    label='Site A11 (Underpass)', zorder=3)
    
    # 全地点のラベル付け
    # 重なりを避けるため、少し右上にオフセット
    for i, row in data.iterrows():
        label = str(row['site_id'])
        x = row['center_x_6677']
        y = row['center_y_6677']
        
        # A11だけ特別扱いして目立たせる
        if label == 'A11':
            plt.text(x + 15, y + 15, label, fontsize=12, fontweight='bold', color='green', zorder=4)
        else:
            plt.text(x + 10, y + 10, label, fontsize=9, color='black', alpha=0.8, zorder=4)

    plt.colorbar(sc, label='Risk Score (0=Safe, 1=Danger)', shrink=0.8)
    plt.title(title, fontsize=16, fontweight='bold')
    plt.xlabel('X Coordinate (m)')
    plt.ylabel('Y Coordinate (m)')
    plt.grid(True, linestyle='--', alpha=0.5, zorder=1)
    plt.axis('equal')
    plt.legend(loc='upper right', fontsize=12)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    # plt.show() # バッチ処理向けにコメントアウト
    plt.close() # メモリ解放
    print(f"Saved plot to: {save_path}")


def generate_spatial_risk_maps(input_csv_path, output_dir):
    """
    リスクマップ生成のメイン処理
    Initial, Phase 1, Phase 2 の3種類のマップを作成する。
    """
    print("=========== SPATIAL RISK MAPPING START ===========")

    # 出力ディレクトリ作成
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"[*] Created output directory: {output_dir}")

    # データの読み込み
    if not os.path.exists(input_csv_path):
        raise FileNotFoundError(f"Input file not found: {input_csv_path}")

    print(f"Loading data from: {input_csv_path}")
    df = pd.read_csv(input_csv_path)

    # A11の位置を特定 (存在チェック付き)
    a11 = None
    if 'site_id' in df.columns:
        # 文字列型に変換して比較
        df['site_id'] = df['site_id'].astype(str)
        a11_rows = df[df['site_id'] == 'A11']
        if not a11_rows.empty:
            a11 = a11_rows.iloc[0]
        else:
            print("[Info] Site 'A11' not found in dataset. Highlighting skipped.")
    
    # --- 1. Initial Risk Map (risk_proxy_5m) ---
    plot_risk_map_with_labels(
        df, 'risk_proxy_5m', 
        '(a) Initial Risk Map (Site Selection Phase)', 
        'figure3_a_initial_labeled.png',
        output_dir, a11
    )

    # --- 2. Phase 1 Result (risk_horizon) ---
    plot_risk_map_with_labels(
        df, 'risk_horizon', 
        '(b) Phase 1 Prediction (Building-Only Model)', 
        'figure3_b_phase1_labeled.png',
        output_dir, a11
    )

    # --- 3. Phase 2 Result (Hybrid) ---
    # Hybridスコア作成 (overhead_flagが存在する場合)
    if 'overhead_flag' in df.columns and 'risk_horizon' in df.columns:
        df['risk_hybrid'] = df.apply(lambda x: 1.0 if x['overhead_flag'] == 1 else x['risk_horizon'], axis=1)
        
        plot_risk_map_with_labels(
            df, 'risk_hybrid', 
            '(c) Phase 2 Prediction (Infrastructure Integrated)', 
            'figure3_c_phase2_labeled.png',
            output_dir, a11
        )
    else:
        print("[Skip] Phase 2 Map: Missing 'overhead_flag' or 'risk_horizon' columns.")

    print("=========== SPATIAL RISK MAPPING DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: src/03_analysis/ (Rootから2階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 入力データパス: ../../data/processed/final_dataset.csv
    # ※ 統一ルールに基づき、final_dataset.csv を参照
    input_data_path = os.path.join(base_dir, "..", "..", "data", "processed", "final_dataset.csv")
    
    # 出力フォルダ: ../../output/figures
    output_figures_dir = os.path.join(base_dir, "..", "..", "output", "figures")

    try:
        generate_spatial_risk_maps(input_data_path, output_figures_dir)
    except Exception as e:
        print(f"Error: {e}")
        print("Please check input file path and columns.")
