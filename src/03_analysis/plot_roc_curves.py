import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, roc_auc_score
import os

# ==========================================
# 0. パス設定
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, '../../data/processed/final_dataset.csv')
OUTPUT_DIR = os.path.join(BASE_DIR, '../../output/figures')

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# 1. データ読み込み
# ==========================================
print(f"Loading data from: {DATA_PATH}")
df = pd.read_csv(DATA_PATH)

# Ground Truth (High Error > 5.0m)
y_true = (df['err_p95_m'] > 5.0).astype(int)

# ==========================================
# 2. スコア定義
# ==========================================
# Phase 1: Building Only (Horizon Risk)
score_p1 = df['risk_horizon']

# Phase 2: Hybrid (Horizon + Overhead)
# もし 'risk_hybrid' カラムがなければ計算する
if 'risk_hybrid' in df.columns:
    score_p2 = df['risk_hybrid']
else:
    score_p2 = df.apply(lambda x: 1.0 if x.get('overhead_flag', 0) == 1 else x['risk_horizon'], axis=1)

# Benchmark: HDOP (符号反転: 小さいほど危険 -> 大きいほど危険)
score_hdop = -df['hdop_cut_a_median']

# ==========================================
# 3. ROC曲線の描画
# ==========================================
plt.figure(figsize=(8, 8))

# --- Phase 2 (Proposed) ---
fpr, tpr, _ = roc_curve(y_true, score_p2)
auc = roc_auc_score(y_true, score_p2)
plt.plot(fpr, tpr, color='#d62728', lw=3, label=f'Phase 2 (Proposed): AUC={auc:.2f}')

# --- Phase 1 (Baseline) ---
fpr, tpr, _ = roc_curve(y_true, score_p1)
auc = roc_auc_score(y_true, score_p1)
plt.plot(fpr, tpr, color='#1f77b4', linestyle='--', lw=2, label=f'Phase 1 (Building-Only): AUC={auc:.2f}')

# --- HDOP (Benchmark) ---
fpr, tpr, _ = roc_curve(y_true, score_hdop)
auc = roc_auc_score(y_true, score_hdop)
plt.plot(fpr, tpr, color='gray', linestyle=':', lw=2, label=f'HDOP (Benchmark): AUC={auc:.2f}')

# ランダム推測線
plt.plot([0, 1], [0, 1], color='navy', linestyle='--', lw=1)

# 装飾
plt.xlim([0.0, 1.0])
plt.ylim([0.0, 1.05])
plt.xlabel('False Positive Rate (1 - Specificity)', fontsize=12)
plt.ylabel('True Positive Rate (Sensitivity)', fontsize=12)
plt.title('Figure 4: ROC Curves Comparison', fontsize=14, fontweight='bold')
plt.legend(loc="lower right", fontsize=11)
plt.grid(alpha=0.3)

# ==========================================
# 4. 保存
# ==========================================
save_path = os.path.join(OUTPUT_DIR, 'figure4_roc_curves.png')
plt.savefig(save_path, dpi=300)
print(f"ROC Curve saved to: {save_path}")