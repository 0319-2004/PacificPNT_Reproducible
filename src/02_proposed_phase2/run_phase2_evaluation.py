import os
import glob
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score
import warnings
warnings.filterwarnings("ignore")

# ==========================================
# 設定
# ==========================================
LOG_DIR = 'logs'
SITE_RISK_FILE = 'week3_analysis2/sites_risk.csv'
DOP_RESULT_FILE = 'week3_dop_results.csv'
DERIVED_DIR = 'week3_analysis2/derived'

# Safety Metrics用設定
HIGH_ERROR_QUANTILE = 0.70 # 上位30%を高誤差とする
FOCUS_SITES = ["A11", "A06"] # A11(高架下), A06(最大誤差)

def parse_gnss_log(filepath):
    # (簡易版) ログからAccuracyだけ抜く
    try:
        df = pd.read_csv(filepath, comment='#', names=['UnixTimeMillis','LatitudeDegrees','LongitudeDegrees','AccuracyMeters'], usecols=[0,1,2,3])
        if df.empty: return None
        # 簡易的な誤差計算（実際は投影変換が必要だが、ここではmerge用のn_fix数カウント等に使用）
        return df
    except:
        return None

def calculate_safety_metrics(df, y_col, score_col, model_name):
    """AUCとSafety Metrics (Rank) を計算"""
    temp = df[[y_col, score_col, 'site_id', 'err_p95_m']].dropna()
    y = temp[y_col].values
    s = temp[score_col].values
    
    if len(np.unique(y)) < 2: return None

    # AUC計算
    auc_raw = roc_auc_score(y, s)
    
    # ランキング用にスコアの向きを揃える (AUC<0.5なら反転)
    flipped = False
    if auc_raw < 0.5:
        s_used = -s
        flipped = True
        auc_used = 1.0 - auc_raw
    else:
        s_used = s
        auc_used = auc_raw

    # ランク付け (高いほど危険)
    temp['_score_used'] = s_used
    temp_sorted = temp.sort_values('_score_used', ascending=False).reset_index(drop=True)
    
    res = {
        "Model": model_name,
        "Score": score_col,
        "AUC": auc_used, # 反転後
        "Flipped": flipped
    }
    
    # 特定サイトの順位
    for site in FOCUS_SITES:
        try:
            rank = temp_sorted[temp_sorted['site_id'] == site].index[0] + 1
            res[f"Rank({site})"] = rank
        except:
            res[f"Rank({site})"] = "-"
            
    return res

def main():
    print("--- Phase 2: Analysis Pipeline (Safety Metrics) ---")
    
    # 1. ログ読み込み & 誤差データ作成 (merged.csv相当を作る)
    # ※今回は簡易的に既存の merged.csv があればそれを使う、なければ作る
    # ここでは「merged_analysis2.csv」を新規作成するフロー
    
    # まずログからサイトID抽出 (本来は全ログ処理だが、簡略化のためRiskファイルベースで結合)
    df_risk = pd.read_csv(SITE_RISK_FILE)
    
    # 誤差データ（既存の merged.csv または site_metrics_raw.csv があると仮定）
    # なければ week3_analysis/derived/latest/merged.csv を探す
    metrics_path = 'week3_analysis/derived/latest/merged.csv'
    if not os.path.exists(metrics_path):
        # ルートにある場合
        metrics_path = 'merged.csv'
    
    if os.path.exists(metrics_path):
        print(f"Loading metrics from: {metrics_path}")
        df_metrics = pd.read_csv(metrics_path)
    else:
        print("Error: merged.csv (Phase 1 result) not found. Run Phase 1 first.")
        return

    # HDOPデータ結合
    if os.path.exists(DOP_RESULT_FILE):
        df_dop = pd.read_csv(DOP_RESULT_FILE)
        df_metrics = pd.merge(df_metrics, df_dop[['site_id', 'hdop_cut_a_median']], on='site_id', how='left')

    # 今回のリスクデータと結合
    # カラム重複を防ぐ
    cols_to_use = [c for c in df_risk.columns if c not in df_metrics.columns or c == 'site_id']
    df_merged = pd.merge(df_metrics, df_risk[cols_to_use], on='site_id', how='inner')
    
    # 保存
    os.makedirs(DERIVED_DIR, exist_ok=True)
    df_merged.to_csv(os.path.join(DERIVED_DIR, 'merged_analysis2_final.csv'), index=False)

    # 2. 評価実行
    # Ground Truth定義
    thr = df_merged['err_p95_m'].quantile(HIGH_ERROR_QUANTILE)
    df_merged['high_error'] = (df_merged['err_p95_m'] >= thr).astype(int)
    
    print(f"High Error Threshold: {thr:.2f}m")
    
    results = []
    # 評価する指標リスト
    targets = [
        ('risk_proxy_5m', 'Phase2 (Combined)'),
        ('risk_horizon',  'Phase2 (Horizon)'),
        ('overhead_score','Phase2 (Overhead)'),
        ('hdop_cut_a_median', 'Benchmark (HDOP)')
    ]
    
    for col, name in targets:
        if col in df_merged.columns:
            res = calculate_safety_metrics(df_merged, 'high_error', col, name)
            if res: results.append(res)
            
    # 結果表示
    res_df = pd.DataFrame(results)
    print("\n=== Final Results for Paper ===")
    print(res_df.to_markdown(index=False))
    
    # ファイル保存
    with open(os.path.join(DERIVED_DIR, 'final_results.txt'), 'w') as f:
        f.write(res_df.to_markdown(index=False))
    print(f"\nResults saved to {DERIVED_DIR}/final_results.txt")

if __name__ == "__main__":
    main()
