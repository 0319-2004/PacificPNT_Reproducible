import os
import glob
import shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import warnings

# 必須ライブラリチェック
try:
    import pyproj
    from sklearn.metrics import roc_curve, auc
except ImportError:
    print("Error: Library missing. Run: pip install pyproj scikit-learn pandas numpy matplotlib")
    exit(1)

# ==========================================
# ユーティリティ関数 (GNSS Parser)
# ==========================================
def parse_gnss_log(filepath):
    fix_lines, status_lines = [], []
    fix_header, status_header = None, None
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line.startswith('# Fix'):
                    fix_header = line.replace('#', '').strip().split(',')
                elif line.startswith('# Status'):
                    status_header = line.replace('#', '').strip().split(',')
                elif line.startswith('Fix'):
                    fix_lines.append(line.split(','))
                elif line.startswith('Status'):
                    status_lines.append(line.split(','))
                    
        if not fix_header or not status_header:
            return None, None, "Missing Header"
            
        df_fix = pd.DataFrame(fix_lines, columns=fix_header)
        df_status = pd.DataFrame(status_lines, columns=status_header)
        
        # 数値変換
        for df, cols in [
            (df_fix, ['UnixTimeMillis', 'LatitudeDegrees', 'LongitudeDegrees', 'AccuracyMeters']),
            (df_status, ['UnixTimeMillis', 'Cn0DbHz', 'ElevationDegrees', 'AzimuthDegrees', 'UsedInFix'])
        ]:
            for c in cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
        
        return df_fix, df_status, "OK"
    except Exception as e:
        return None, None, str(e)

def calculate_projected_error(df_fix, transformer):
    if df_fix.empty: return np.nan, np.nan
    valid = df_fix.dropna(subset=['LatitudeDegrees', 'LongitudeDegrees'])
    if valid.empty: return np.nan, np.nan
    
    # pyproj.Transformer (always_xy=True) -> lon, lat
    xx, yy = transformer.transform(valid['LongitudeDegrees'].values, valid['LatitudeDegrees'].values)
    
    med_x, med_y = np.median(xx), np.median(yy)
    dists = np.sqrt((xx - med_x)**2 + (yy - med_y)**2)
    return np.percentile(dists, 50), np.percentile(dists, 95)

def calculate_hdop_from_geometry(az, el):
    if len(az) < 4: return np.nan
    az_rad, el_rad = np.radians(az), np.radians(el)
    # G matrix for HDOP
    G = np.column_stack([
        -np.cos(el_rad)*np.sin(az_rad), 
        -np.cos(el_rad)*np.cos(az_rad), 
        -np.sin(el_rad), 
        np.ones_like(az_rad)
    ])
    try:
        Q = np.linalg.inv(G.T @ G)
        return np.sqrt(Q[0, 0] + Q[1, 1])
    except:
        return np.nan


# ==========================================
# メイン解析ロジック
# ==========================================
def run_baseline_analysis(
    log_dir, 
    site_def_file, 
    output_dir, 
    qc_min_epochs=240, 
    qc_min_duration=240.0,
    proj_epsg="epsg:6677",
    high_error_quantile=0.70
):
    print("--- Baseline Pipeline Started ---")
    
    # 出力ディレクトリ準備
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = os.path.join(output_dir, 'runs', timestamp)
    latest_dir = os.path.join(output_dir, 'latest')
    
    if os.path.exists(latest_dir):
        shutil.rmtree(latest_dir)
    os.makedirs(os.path.join(run_dir, 'plots'), exist_ok=True)
    os.makedirs(os.path.join(latest_dir, 'plots'), exist_ok=True)

    # 座標変換設定 (x=lon, y=lat)
    transformer = pyproj.Transformer.from_crs("epsg:4326", proj_epsg, always_xy=True)

    # ログファイルの検索 (rawフォルダ直下の .txt)
    log_files = glob.glob(os.path.join(log_dir, '*.txt'))
    print(f"Found {len(log_files)} logs in {log_dir}")
    
    qc_fails, site_metrics = [], []
    
    for filepath in log_files:
        site_id = os.path.basename(filepath).split('_')[0]
        df_fix, df_status, msg = parse_gnss_log(filepath)
        
        if df_fix is None:
            qc_fails.append({'site_id': site_id, 'reason': f"Parse Error: {msg}"})
            continue
            
        t_min, t_max = df_fix['UnixTimeMillis'].min(), df_fix['UnixTimeMillis'].max()
        duration = (t_max - t_min) / 1000.0 if pd.notnull(t_min) else 0
        n_fix = len(df_fix)
        
        # QC Check
        if n_fix < qc_min_epochs:
            qc_fails.append({'site_id': site_id, 'reason': f"Low Epochs ({n_fix})"})
            continue
        if duration < qc_min_duration:
            qc_fails.append({'site_id': site_id, 'reason': f"Short Duration ({duration:.1f}s)"})
            continue
            
        err_p50, err_p95 = calculate_projected_error(df_fix, transformer)
        
        # Status Metrics
        df_used = df_status[df_status['UsedInFix'] == 1].copy()
        if df_used.empty:
             qc_fails.append({'site_id': site_id, 'reason': "No Used Satellites"})
             continue

        grp_used = df_used.groupby('UnixTimeMillis')
        used_sat_mean = grp_used.size().mean()
        
        # HDOP Calculation
        hdop_results = {}
        for cut_name, min_el in [('hdop_cut_a', 5), ('hdop_cut_b', 15)]:
            df_cut = df_status[df_status['ElevationDegrees'] >= min_el]
            hdops = []
            if not df_cut.empty:
                for t, g in df_cut.groupby('UnixTimeMillis'):
                    if 'AzimuthDegrees' in g.columns:
                        val = calculate_hdop_from_geometry(g['AzimuthDegrees'].values, g['ElevationDegrees'].values)
                        if not np.isnan(val) and val < 50: hdops.append(val)
            hdop_results[f"{cut_name}_median"] = np.median(hdops) if hdops else np.nan

        site_metrics.append({
            'site_id': site_id, 'err_p95_m': err_p95, 'err_p50_m': err_p50,
            'n_fix': n_fix, 'duration': duration, 'used_sat_mean': used_sat_mean,
            'cn0_mean': df_used['Cn0DbHz'].mean(), 'cn0_std': df_used['Cn0DbHz'].std(),
            'elev_mean': df_used['ElevationDegrees'].mean(),
            'used_rate': len(df_used)/len(df_status) if len(df_status) > 0 else 0,
            'hdop_cut_a_median': hdop_results['hdop_cut_a_median'],
            'hdop_cut_b_median': hdop_results['hdop_cut_b_median']
        })
        print(f"Processed {site_id}: err95={err_p95:.2f}m")

    if qc_fails:
        pd.DataFrame(qc_fails).to_csv(os.path.join(run_dir, 'qc_fails.csv'), index=False)
    
    if not site_metrics:
        print("No sites passed QC.")
        return

    df_metrics = pd.DataFrame(site_metrics)
    # 中間ファイル保存
    df_metrics.to_csv(os.path.join(run_dir, 'site_metrics_raw.csv'), index=False)
    
    # --- Merge with Site Definitions (Corrected) ---
    if not os.path.exists(site_def_file):
        print(f"Warning: {site_def_file} not found. Skipping merge.")
        # ファイルがない場合は解析結果のみを出力
        output_csv_name = 'final_dataset.csv'
        df_metrics.to_csv(os.path.join(run_dir, output_csv_name), index=False)
        return
        
    df_risk = pd.read_csv(site_def_file)
    df_risk['site_id'] = df_risk['site_id'].astype(str).str.strip()
    
    # 内部結合 (サイト定義にある場所のみ残す)
    df_merged = pd.merge(df_metrics, df_risk, on='site_id', how='inner')
    print(f"Merged with definitions: {len(df_merged)} sites")
    
    # 出力ファイル名は統一ルール 'final_dataset.csv'
    output_csv_name = 'final_dataset.csv'
    df_merged.to_csv(os.path.join(run_dir, output_csv_name), index=False)
    
    # --- Analysis & Plotting ---
    if 'err_p95_m' in df_merged.columns:
        thr = df_merged['err_p95_m'].quantile(high_error_quantile)
        df_merged['high_error'] = (df_merged['err_p95_m'] >= thr).astype(int)
        print(f"High Error Threshold (top {100*(1-high_error_quantile):.0f}%): {thr:.2f}m")
    
    # プロット用の特徴量 (定義ファイルに含まれている場合のみ使用)
    possible_features = ['risk_proxy_5m', 'svf_proxy_5m', 'risk_cut5', 'hdop_cut_a_median', 'hdop_cut_b_median']
    features = [f for f in possible_features if f in df_merged.columns]
    
    if features:
        auc_results = []
        plt.figure(figsize=(8, 8))
        for f in features:
            tmp = df_merged[[f, 'high_error']].dropna()
            if len(tmp['high_error'].unique()) < 2: continue
            fpr, tpr, _ = roc_curve(tmp['high_error'], tmp[f])
            score = auc(fpr, tpr)
            plt.plot(fpr, tpr, label=f'{f} (AUC={score:.2f})')
            auc_results.append(f"{f}: {score:.3f}")
            
        plt.plot([0,1],[0,1],'k--'); plt.legend(); plt.title('ROC Curves')
        plt.savefig(os.path.join(run_dir, 'plots', 'roc_curves.png'))
        with open(os.path.join(run_dir, 'roc_auc.txt'), 'w') as f: f.write('\n'.join(auc_results))
        
        # Scatter Plots
        plt.figure(figsize=(15, 5))
        for i, f in enumerate(features[:3]):
            plt.subplot(1, 3, i+1)
            plt.scatter(df_merged[f], df_merged['err_p95_m'], alpha=0.6)
            plt.xlabel(f); plt.ylabel('Error p95 (m)')
        plt.tight_layout()
        plt.savefig(os.path.join(run_dir, 'plots', 'scatter_risk_err.png'))
    else:
        print("[Info] Risk proxy columns not found in site definitions. Skipping plots.")

    # Copy results to 'latest'
    for f in glob.glob(os.path.join(run_dir, '*')):
        if os.path.isfile(f):
            shutil.copy(f, latest_dir)
            
    for plot_file in glob.glob(os.path.join(run_dir, 'plots', '*')):
        shutil.copy(plot_file, os.path.join(latest_dir, 'plots'))

    print(f"\nCompleted. Results in: {latest_dir}")


if __name__ == "__main__":
    # ファイル配置場所: src/01_baseline_phase1/
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 【修正1】ログ入力パス: ../../data/raw/gnss_logs (ファイル構成に合わせる)
    log_input_dir = os.path.join(base_dir, "..", "..", "data", "raw", "gnss_logs")
    
    # 【修正2】サイト定義パス: ../../data/raw/site_definitions.csv (ファイル名統一)
    site_def_csv = os.path.join(base_dir, "..", "..", "data", "raw", "site_definitions.csv")
    
    # 出力先
    output_base_dir = os.path.join(base_dir, "..", "..", "output", "baseline_analysis")
    
    # 実行
    run_baseline_analysis(
        log_dir=log_input_dir,
        site_def_file=site_def_csv,
        output_dir=output_base_dir,
        qc_min_epochs=240,
        qc_min_duration=240.0,
        proj_epsg="epsg:6677",
        high_error_quantile=0.70
    )
