import os
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score
import warnings

# 警告抑制
warnings.filterwarnings("ignore")

# ==========================================
# 定数・設定
# ==========================================
HIGH_ERROR_QUANTILE = 0.70  # 上位30%を高誤差（危険）とする
FOCUS_SITES = ["A11", "A06"] # 特定の注目サイト（A11:高架下, A06:最大誤差）

# ==========================================
# ヘルパー関数
# ==========================================
def calculate_safety_metrics(df, y_col, score_col, model_name, focus_sites=FOCUS_SITES):
    """
    指定されたスコアについてAUCとSafety Metrics (Rank) を計算する。
    AUC < 0.5 の場合はスコアの正負を反転して評価する。
    """
    # 必要なカラムのみ抽出して欠損除去
    cols = [y_col, score_col, 'site_id', 'err_p95_m']
    # カラムが存在しない場合はスキップ
    if score_col not in df.columns:
        return None
        
    temp = df[cols].dropna()
    
    y = temp[y_col].values
    s = temp[score_col].values
    
    # クラスが1つしかない場合は計算不可
    if len(np.unique(y)) < 2:
        return None

    # AUC計算
    try:
        auc_raw = roc_auc_score(y, s)
    except ValueError:
        return None
    
    # ランキング用にスコアの向きを揃える (AUC < 0.5 ならスコアが高いほど安全という意味なので反転)
    flipped = False
    if auc_raw < 0.5:
        s_used = -s
        flipped = True
        auc_used = 1.0 - auc_raw
    else:
        s_used = s
        auc_used = auc_raw

    # ランク付け (スコアが高いほど危険 = 高ランク)
    temp = temp.copy()
    temp['_score_used'] = s_used
    temp_sorted = temp.sort_values('_score_used', ascending=False).reset_index(drop=True)
    
    res = {
        "Model": model_name,
        "Score": score_col,
        "AUC": round(auc_used, 3),
        "Flipped": flipped
    }
    
    # 特定サイトの順位を取得
    for site in focus_sites:
        try:
            # 1-based index (site_idを文字列として比較)
            match = temp_sorted[temp_sorted['site_id'].astype(str) == str(site)]
            if not match.empty:
                rank = match.index[0] + 1
                res[f"Rank({site})"] = rank
            else:
                res[f"Rank({site})"] = "-"
        except IndexError:
            res[f"Rank({site})"] = "-"
            
    return res

# ==========================================
# メイン処理関数
# ==========================================
def run_phase2_evaluation(risk_csv_path, baseline_metrics_path, dop_csv_path, output_dir, final_dataset_path):
    print("--- Phase 2: Analysis Pipeline (Safety Metrics) ---")
    
    # 出力ディレクトリ作成
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # final_dataset.csv の保存先ディレクトリ作成
    final_data_dir = os.path.dirname(final_dataset_path)
    if not os.path.exists(final_data_dir):
        os.makedirs(final_data_dir, exist_ok=True)

    # 1. ファイル読み込み
    # Phase 2 Risk (今回計算した指標)
    if not os.path.exists(risk_csv_path):
        raise FileNotFoundError(f"Risk metrics file not found: {risk_csv_path}\nPlease run calc_phase2_risk.py first.")
    df_risk = pd.read_csv(risk_csv_path)
    # サイトIDを文字列型に統一
    df_risk['site_id'] = df_risk['site_id'].astype(str)

    # Phase 1 Metrics (誤差正解データ: err_p95_m)
    if not os.path.exists(baseline_metrics_path):
        raise FileNotFoundError(f"Baseline metrics file not found: {baseline_metrics_path}")
    df_metrics = pd.read_csv(baseline_metrics_path)
    df_metrics['site_id'] = df_metrics['site_id'].astype(str)
    
    print(f"Loaded Risk Data: {len(df_risk)} sites")
    print(f"Loaded Baseline Data: {len(df_metrics)} sites")

    # 2. データの結合
    # DOPデータ (HDOP Benchmark用) は任意
    if os.path.exists(dop_csv_path):
        df_dop = pd.read_csv(dop_csv_path)
        df_dop['site_id'] = df_dop['site_id'].astype(str)
        # 必要なカラムだけ結合
        if 'hdop_cut_a_median' in df_dop.columns:
            df_metrics = pd.merge(df_metrics, df_dop[['site_id', 'hdop_cut_a_median']], on='site_id', how='left')
            print("Merged DOP data.")
    else:
        print(f"Warning: DOP file not found ({dop_csv_path}). Skipping HDOP benchmark.")

    # Riskデータと結合 (Phase 1の結果をベースに Phase 2のスコアを付与)
    # カラム重複を防ぐため、df_riskからはmetricsに含まれていないカラムのみ採用
    cols_to_use = [c for c in df_risk.columns if c not in df_metrics.columns or c == 'site_id']
    df_merged = pd.merge(df_metrics, df_risk[cols_to_use], on='site_id', how='inner')
    
    print(f"Merged Data: {len(df_merged)} sites")
    
    # 【重要】最終データセットを data/processed/final_dataset.csv として保存
    df_merged.to_csv(final_dataset_path, index=False)
    print(f"Saved final dataset to: {final_dataset_path}")

    # 3. 評価実行 (High Error Ground Truthの定義)
    if 'err_p95_m' not in df_merged.columns:
        print("Error: 'err_p95_m' column missing. Cannot evaluate.")
        return

    thr = df_merged['err_p95_m'].quantile(HIGH_ERROR_QUANTILE)
    df_merged['high_error'] = (df_merged['err_p95_m'] >= thr).astype(int)
    
    print(f"High Error Threshold (top {100*(1-HIGH_ERROR_QUANTILE):.0f}%): {thr:.2f}m")
    
    results = []
    # 評価対象の指標リスト
    targets = [
        ('risk_proxy_5m', 'Phase2 (Combined)'),
        ('risk_horizon',  'Phase2 (Horizon)'),
        ('overhead_score','Phase2 (Overhead)'),
        ('hdop_cut_a_median', 'Benchmark (HDOP)')
    ]
    
    for col, name in targets:
        if col in df_merged.columns:
            res = calculate_safety_metrics(df_merged, 'high_error', col, name)
            if res:
                results.append(res)
        else:
            print(f"Skipping {name}: Column '{col}' not found.")
            
    # 4. 結果表示と保存
    if not results:
        print("No results calculated.")
        return

    res_df = pd.DataFrame(results)
    
    # コンソール表示
    print("\n=== Final Results for Paper ===")
    try:
        print(res_df.to_string(index=False))
    except:
        print(res_df)
    
    # テキストファイル保存
    result_txt_path = os.path.join(output_dir, 'final_results.txt')
    with open(result_txt_path, 'w', encoding='utf-8') as f:
        f.write(res_df.to_string(index=False))
        
    print(f"\nResults saved to {result_txt_path}")


if __name__ == "__main__":
    # ファイル配置場所: src/02_proposed_phase2/ (Rootから2階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # =========================================================
    # 1. 入力ファイルの「優先順位」設定 (Dual Path Logic)
    # =========================================================
    
    # Plan A: ユーザーが run_baseline.py で「今」生成したデータ (再現性確認用)
    baseline_generated = os.path.join(base_dir, "..", "..", "output", "baseline_analysis", "latest", "final_dataset.csv")
    
    # Plan B: リポジトリに同梱されている「正解」データ (動作保証用)
    baseline_provided = os.path.join(base_dir, "..", "..", "data", "processed", "final_dataset.csv")

    # 自動判定ロジック
    if os.path.exists(baseline_generated):
        print(f"[*] Using GENERATED baseline data (Plan A): {os.path.basename(baseline_generated)}")
        input_baseline_csv = baseline_generated
    elif os.path.exists(baseline_provided):
        print(f"[*] Using PROVIDED baseline data (Plan B): {os.path.basename(baseline_provided)}")
        input_baseline_csv = baseline_provided
    else:
        # どちらもない場合はエラー (Phase 1を実行してください)
        input_baseline_csv = baseline_generated # エラーメッセージ用にPlan Aのパスを設定

    # =========================================================
    # 2. その他のパス設定
    # =========================================================
    
    # Risk結果: output/phase2_risk/sites_risk.csv (calc_phase2_risk.py の出力)
    input_risk_csv = os.path.join(base_dir, "..", "..", "output", "phase2_risk", "sites_risk.csv")
    
    # DOP結果 (あれば)
    input_dop_csv = os.path.join(base_dir, "..", "..", "output", "baseline_analysis", "week3_dop_results.csv")
    
    # 出力先: output/phase2_evaluation
    output_eval_dir = os.path.join(base_dir, "..", "..", "output", "phase2_evaluation")
    
    # 【重要】最終データセット保存先: data/processed/final_dataset.csv (上書き)
    final_dataset_dest = os.path.join(base_dir, "..", "..", "data", "processed", "final_dataset.csv")
    
    # 実行
    try:
        run_phase2_evaluation(
            risk_csv_path=input_risk_csv,
            baseline_metrics_path=input_baseline_csv,
            dop_csv_path=input_dop_csv,
            output_dir=output_eval_dir,
            final_dataset_path=final_dataset_dest
        )
    except Exception as e:
        print(f"Error during evaluation: {e}")
        print("Ensure that Phase 1 (baseline) and Phase 2 (risk calculation) have been executed successfully.")
