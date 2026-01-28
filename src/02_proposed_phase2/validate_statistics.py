import os
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

# 警告抑制 (SeabornのFutureWarning等)
warnings.filterwarnings("ignore")

def validate_statistics(input_csv_path, output_dir):
    """
    Phase 2 (提案手法) と HDOP (ベンチマーク) のAUC差分について、
    ブートストラップ法を用いた統計的有意差検定を行う。
    """
    print("=========== STATISTICAL VALIDATION START ===========")

    # 出力先作成
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"[*] Created output directory: {output_dir}")

    # データ読み込み
    if not os.path.exists(input_csv_path):
        raise FileNotFoundError(f"Input file not found: {input_csv_path}")

    print(f"Loading data from: {input_csv_path}")
    df = pd.read_csv(input_csv_path)

    # ==========================================
    # 1. データ準備と正解ラベルの定義
    # ==========================================
    # データの量子化を考慮し、5.0mを超えるものを「明確なハザード」とする
    threshold = 5.0
    
    # 必要なカラムの存在確認
    required_cols = ['err_p95_m', 'overhead_flag', 'risk_horizon', 'hdop_cut_a_median']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column in dataset: {col}")

    # 正解ラベル作成
    y_true = (df['err_p95_m'] > threshold).astype(int)

    print(f"Total Sites: {len(df)}")
    print(f"High Risk Sites (> {threshold}m): {y_true.sum()}")

    # ==========================================
    # 2. スコアの定義
    # ==========================================
    # Phase 2 (Hybrid): 高架下(overhead=1)ならリスク最大(1.0)に強制
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
        # 重複を許してランダムにリサンプリング
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
    diffs_arr = np.array(diffs)
    p_value = (diffs_arr <= 0).mean()

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
    out_txt_path = os.path.join(output_dir, 'stats_validation_results.txt')
    with open(out_txt_path, 'w') as f:
        f.write(result_txt)

    # ==========================================
    # 5. 分布の可視化と保存
    # ==========================================
    plt.figure(figsize=(8, 5))
    sns.histplot(diffs_arr, kde=True, color='purple', label='Difference (P2 - HDOP)')
    plt.axvline(0, color='red', linestyle='--', label='Zero Difference')
    plt.title(f'Distribution of AUC Differences (Bootstrap n={n_bootstraps})\nP-value: {p_value:.4f}')
    plt.xlabel('AUC Difference (Phase 2 - HDOP)')
    plt.legend()
    plt.tight_layout()

    # 画像保存
    plot_path = os.path.join(output_dir, 'auc_difference_bootstrap.png')
    plt.savefig(plot_path)
    print(f"Plot saved to: {plot_path}")
    print("=========== STATISTICAL VALIDATION DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: src/02_proposed_phase2/ (Rootから2階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 入力: ../../data/processed/final_dataset.csv (統一ルールに基づく)
    input_csv = os.path.join(base_dir, "..", "..", "data", "processed", "final_dataset.csv")
    
    # 出力: ../../output/phase2_proposed
    output_dir = os.path.join(base_dir, "..", "..", "output", "phase2_proposed")

    try:
        validate_statistics(input_csv, output_dir)
    except Exception as e:
        print(f"Error: {e}")
        print("Ensure 'final_dataset.csv' exists in data/processed/.")
