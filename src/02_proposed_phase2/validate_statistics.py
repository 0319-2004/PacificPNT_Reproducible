cat << 'EOF' > PacificPNT_Reproducible/src/02_proposed_phase2/validate_statistics.py
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score
import matplotlib.pyplot as plt
import seaborn as sns
import os

# ==========================================
# 0. 設定とデータ読み込み
# ==========================================
# リポジトリ構造に合わせたパス設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, '../../data/processed/final_dataset.csv')
OUTPUT_DIR = os.path.join(BASE_DIR, '../../output/phase2_proposed')

# 出力先がなければ作成
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"Loading data from: {DATA_PATH}")
df = pd.read_csv(DATA_PATH)

# ==========================================
# 1. データ準備と正解ラベルの定義 (Strict Threshold)
# ==========================================
# データの量子化を考慮し、5.0mを超えるものを「明確なハザード」とする
threshold = 5.0
y_true = (df['err_p95_m'] > threshold).astype(int)

print(f"Total Sites: {len(df)}")
print(f"High Risk Sites (> {threshold}m): {y_true.sum()}")

# ==========================================
# 2. スコアの定義
# ==========================================
# Phase 2 (Hybrid): 高架下(overhead=1)ならリスク最大(1.0)に強制
# ※ overhead_flagがない場合は計算して補完するロジックを入れても良いが、
#    ここではfinal_datasetにカラムがある前提とする
score_p2 = np.where(df['overhead_flag'] == 1, 1.0, df['risk_horizon'])

# HDOP (Benchmark):
# 「高誤差の場所ほどHDOPが低い（良好に見える）」という逆相関への対応。
# 符号を反転させ、「数値が大きい＝リスクが高い」に定義を揃える。
score_hdop = -df['hdop_cut_a_median']

# ==========================================
# 3. Bootstrap法による信頼区間と有意差検定
# ==========================================
n_bootstraps = 10000
aucs_p2 = []
aucs_hdop = []
diffs = [] # (Phase 2 - HDOP) の差分

rng = np.random.RandomState(42) # 再現性のためシード固定

print(f"--- Bootstrapping (n={n_bootstraps}) ---")

for i in range(n_bootstraps):
    # 重複を許してランダムにリサンプリング (N=45)
    indices = rng.randint(0, len(y_true), len(y_true))
    
    # 正解ラベルが「全て0」または「全て1」になった場合は計算できないのでスキップ
    if len(np.unique(y_true[indices])) < 2:
        continue
    
    # AUCを計算
    auc1 = roc_auc_score(y_true[indices], score_p2[indices])
    auc2 = roc_auc_score(y_true[indices], score_hdop[indices])
    
    aucs_p2.append(auc1)
    aucs_hdop.append(auc2)
    diffs.append(auc1 - auc2) # ペアごとの差分を記録

# ==========================================
# 4. 結果の集計と保存
# ==========================================
# 95%信頼区間
p2_ci = np.percentile(aucs_p2, [2.5, 97.5])
hdop_ci = np.percentile(aucs_hdop, [2.5, 97.5])

# p値 (片側検定): 差分が0以下だった割合
diffs = np.array(diffs)
p_value = (diffs <= 0).mean()

# 結果テキストの作成
result_txt = (
    f"--- Statistical Validation Results ---\n"
    f"Samples: {len(df)}\n"
    f"Bootstrap Iterations: {n_bootstraps}\n\n"
    f"Phase 2 AUC: {np.mean(aucs_p2):.3f} [95% CI: {p2_ci[0]:.3f} - {p2_ci[1]:.3f}]\n"
    f"HDOP AUC   : {np.mean(aucs_hdop):.3f} [95% CI: {hdop_ci[0]:.3f} - {hdop_ci[1]:.3f}]\n"
    f"P-value (Phase 2 > HDOP): {p_value:.4f}\n"
)

# コンソール出力
print(result_txt)

# テキスト保存
with open(os.path.join(OUTPUT_DIR, 'stats_validation_results.txt'), 'w') as f:
    f.write(result_txt)

# ==========================================
# 5. 分布の可視化と保存
# ==========================================
plt.figure(figsize=(8, 5))
sns.histplot(diffs, kde=True, color='purple', label='Difference (P2 - HDOP)')
plt.axvline(0, color='red', linestyle='--', label='Zero Difference')
plt.title(f'Distribution of AUC Differences (Bootstrap n={n_bootstraps})\nP-value: {p_value:.4f}')
plt.xlabel('AUC Difference (Phase 2 - HDOP)')
plt.legend()
plt.tight_layout()

# 画像保存
plot_path = os.path.join(OUTPUT_DIR, 'auc_difference_bootstrap.png')
plt.savefig(plot_path)
print(f"Plot saved to: {plot_path}")
EOF