import os
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, roc_auc_score

def plot_roc_comparison(input_csv, output_dir):
    """
    指定されたデータセットから ROC曲線を描画し、Phase 1, Phase 2, HDOP の精度を比較する。
    画像は output_dir に保存される。
    """
    print("=========== ROC CURVE PLOTTING START ===========")

    # 出力先ディレクトリ作成
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"[*] Created output directory: {output_dir}")

    # データ読み込み
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"Input file not found: {input_csv}")

    print(f"Loading data from: {input_csv}")
    df = pd.read_csv(input_csv)

    # ==========================================
    # 1. データ準備 (Ground Truth)
    # ==========================================
    # Ground Truth (High Error > 5.0m)
    if 'err_p95_m' not in df.columns:
        raise ValueError("Dataset missing 'err_p95_m' column.")
        
    y_true = (df['err_p95_m'] > 5.0).astype(int)
    print(f"Total samples: {len(df)}")
    print(f"High risk samples (>5.0m): {y_true.sum()}")

    # ==========================================
    # 2. スコア定義
    # ==========================================
    # Phase 1: Building Only (Horizon Risk)
    if 'risk_horizon' not in df.columns:
        print("[Warning] 'risk_horizon' column not found. Phase 1 curve will be skipped.")
        score_p1 = None
    else:
        score_p1 = df['risk_horizon']

    # Phase 2: Hybrid (Horizon + Overhead)
    # もし 'risk_hybrid' カラムがなければ計算する (overhead_flag=1なら1.0, それ以外はhorizon)
    if 'risk_hybrid' in df.columns:
        score_p2 = df['risk_hybrid']
    elif 'overhead_flag' in df.columns and score_p1 is not None:
        score_p2 = df.apply(lambda x: 1.0 if x.get('overhead_flag', 0) == 1 else x['risk_horizon'], axis=1)
    else:
        print("[Warning] Cannot calculate Phase 2 score (missing columns).")
        score_p2 = None

    # Benchmark: HDOP (符号反転: 小さいほど危険 -> 大きいほど危険)
    if 'hdop_cut_a_median' in df.columns:
        score_hdop = -df['hdop_cut_a_median']
    else:
        print("[Warning] 'hdop_cut_a_median' not found. Benchmark curve will be skipped.")
        score_hdop = None

    # ==========================================
    # 3. ROC曲線の描画
    # ==========================================
    plt.figure(figsize=(8, 8))

    # --- Phase 2 (Proposed) ---
    if score_p2 is not None:
        fpr, tpr, _ = roc_curve(y_true, score_p2)
        auc = roc_auc_score(y_true, score_p2)
        plt.plot(fpr, tpr, color='#d62728', lw=3, label=f'Phase 2 (Proposed): AUC={auc:.2f}')

    # --- Phase 1 (Baseline) ---
    if score_p1 is not None:
        fpr, tpr, _ = roc_curve(y_true, score_p1)
        auc = roc_auc_score(y_true, score_p1)
        plt.plot(fpr, tpr, color='#1f77b4', linestyle='--', lw=2, label=f'Phase 1 (Building-Only): AUC={auc:.2f}')

    # --- HDOP (Benchmark) ---
    if score_hdop is not None:
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
    save_path = os.path.join(output_dir, 'figure4_roc_curves.png')
    plt.savefig(save_path, dpi=300)
    print(f"ROC Curve saved to: {save_path}")
    print("=========== ROC CURVE PLOTTING DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: src/03_analysis/ (Rootから2階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 入力データパス: ../../data/processed/final_dataset.csv
    # ※もし前工程の出力 (merged_analysis2_final.csv) を使う場合はパスを適宜変更してください
    input_data_path = os.path.join(base_dir, "..", "..", "data", "processed", "final_dataset.csv")

    # 出力フォルダ: ../../output/figures
    output_figures_dir = os.path.join(base_dir, "..", "..", "output", "figures")

    try:
        plot_roc_comparison(input_data_path, output_figures_dir)
    except Exception as e:
        print(f"Error: {e}")
        print("Please check if the input CSV exists and contains required columns.")
