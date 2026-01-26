import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# データの読み込み
df = pd.read_csv('merged_analysis2_final.csv')

# A11の位置を特定
a11 = df[df['site_id'] == 'A11'].iloc[0]

def plot_risk_map_with_labels(data, value_col, title, filename):
    plt.figure(figsize=(12, 12))  # ラベルが見やすいようにサイズアップ
    plt.style.use('default')
    
    # メインの散布図 (青->赤)
    sc = plt.scatter(data['center_x_6677'], data['center_y_6677'], 
                     c=data[value_col], cmap='coolwarm', 
                     s=150, edgecolors='black', vmin=0, vmax=1.0, zorder=2)
    
    # A11の強調 (緑の丸)
    plt.scatter(a11['center_x_6677'], a11['center_y_6677'], 
                s=500, facecolors='none', edgecolors='#00FF00', linewidth=3, 
                label='Site A11 (Underpass)', zorder=3)
    
    # 全地点のラベル付け
    # 重なりを避けるため、少し右上にオフセット
    for i, row in data.iterrows():
        label = row['site_id']
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
    plt.savefig(filename, dpi=300)
    plt.show()

# --- 1. Initial Risk Map (risk_proxy_5m) ---
plot_risk_map_with_labels(df, 'risk_proxy_5m', 
                          '(a) Initial Risk Map (Site Selection Phase)', 
                          'figure3_a_initial_labeled.png')

# --- 2. Phase 1 Result (risk_horizon) ---
plot_risk_map_with_labels(df, 'risk_horizon', 
                          '(b) Phase 1 Prediction (Building-Only Model)', 
                          'figure3_b_phase1_labeled.png')

# --- 3. Phase 2 Result (Hybrid) ---
# Hybridスコア作成
df['risk_hybrid'] = df.apply(lambda x: 1.0 if x['overhead_flag'] == 1 else x['risk_horizon'], axis=1)

plot_risk_map_with_labels(df, 'risk_hybrid', 
                          '(c) Phase 2 Prediction (Infrastructure Integrated)', 
                          'figure3_c_phase2_labeled.png')