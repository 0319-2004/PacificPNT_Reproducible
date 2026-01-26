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
# 設定
# ==========================================
LOG_DIR = 'logs'
SITE_RISK_FILE = '../sites_risk.csv'  # 親ディレクトリを参照
DERIVED_DIR = 'derived'

# QC設定
QC_MIN_EPOCHS = 240
QC_MIN_DURATION = 240.0

# 投影座標系 (ユーザー指定: EPSG:6677)
PROJ_EPSG = "epsg:6677" 
HIGH_ERROR_QUANTILE = 0.70

def setup_directories():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = os.path.join(DERIVED_DIR, 'runs', timestamp)
    latest_dir = os.path.join(DERIVED_DIR, 'latest')
    for d in [run_dir, latest_dir]:
        if os.path.exists(d) and d == latest_dir:
            shutil.rmtree(d)
        os.makedirs(os.path.join(d, 'plots'), exist_ok=True)
    return run_dir, latest_dir

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
                    
        if not fix_header or not status_header: return None, None, "Missing Header"
            
        df_fix = pd.DataFrame(fix_lines, columns=fix_header)
        df_status = pd.DataFrame(status_lines, columns=status_header)
        
        # 数値変換
        for df, cols in [
            (df_fix, ['UnixTimeMillis', 'LatitudeDegrees', 'LongitudeDegrees', 'AccuracyMeters']),
            (df_status, ['UnixTimeMillis', 'Cn0DbHz', 'ElevationDegrees', 'AzimuthDegrees', 'UsedInFix'])
        ]:
            for c in cols:
                if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
        
        return df_fix, df_status, "OK"
    except Exception as e:
        return None, None, str(e)

def calculate_projected_error(df_fix, transformer):
    if df_fix.empty: return np.nan, np.nan
    valid = df_fix.dropna(subset=['LatitudeDegrees', 'LongitudeDegrees'])
    if valid.empty: return np.nan, np.nan
    
    # 修正箇所: always_xy=True なので (Longitude, Latitude) の順で渡す
    xx, yy = transformer.transform(valid['LongitudeDegrees'].values, valid['LatitudeDegrees'].values)
    
    med_x, med_y = np.median(xx), np.median(yy)
    dists = np.sqrt((xx - med_x)**2 + (yy - med_y)**2)
    return np.percentile(dists, 50), np.percentile(dists, 95)

def calculate_hdop_from_geometry(az, el):
    if len(az) < 4: return np.nan
    az_rad, el_rad = np.radians(az), np.radians(el)
    G = np.column_stack([-np.cos(el_rad)*np.sin(az_rad), -np.cos(el_rad)*np.cos(az_rad), -np.sin(el_rad), np.ones_like(az_rad)])
    try:
        Q = np.linalg.inv(G.T @ G)
        return np.sqrt(Q[0, 0] + Q[1, 1])
    except: return np.nan

def main():
    print("--- Pipeline Started ---")
    run_dir, latest_dir = setup_directories()
    
    # 座標変換設定 (x=lon, y=lat)
    transformer = pyproj.Transformer.from_crs("epsg:4326", PROJ_EPSG, always_xy=True)

    log_files = glob.glob(os.path.join(LOG_DIR, '*.txt'))
    print(f"Found {len(log_files)} logs in {LOG_DIR}")
    
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
        
        if n_fix < QC_MIN_EPOCHS:
            qc_fails.append({'site_id': site_id, 'reason': f"Low Epochs ({n_fix})"})
            continue
        if duration < QC_MIN_DURATION:
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
            'site_id': site_id, 'err_p50_m': err_p50, 'err_p95_m': err_p95,
            'n_fix': n_fix, 'duration': duration, 'used_sat_mean': used_sat_mean,
            'cn0_mean': df_used['Cn0DbHz'].mean(), 'cn0_std': df_used['Cn0DbHz'].std(),
            'elev_mean': df_used['ElevationDegrees'].mean(),
            'used_rate': len(df_used)/len(df_status) if len(df_status) > 0 else 0,
            'hdop_cut_a_median': hdop_results['hdop_cut_a_median'],
            'hdop_cut_b_median': hdop_results['hdop_cut_b_median']
        })
        print(f"Processed {site_id}: err95={err_p95:.2f}m")

    if qc_fails: pd.DataFrame(qc_fails).to_csv(os.path.join(run_dir, 'qc_fails.csv'), index=False)
    
    if not site_metrics:
        print("No sites passed QC.")
        return

    df_metrics = pd.DataFrame(site_metrics)
    df_metrics.to_csv(os.path.join(run_dir, 'site_metrics_raw.csv'), index=False)
    
    if not os.path.exists(SITE_RISK_FILE):
        print(f"Warning: {SITE_RISK_FILE} not found. Skipped merge.")
        return
        
    df_risk = pd.read_csv(SITE_RISK_FILE)
    df_risk['site_id'] = df_risk['site_id'].astype(str).str.strip()
    df_merged = pd.merge(df_metrics, df_risk, on='site_id', how='inner')
    print(f"Merged: {len(df_merged)} sites")
    df_merged.to_csv(os.path.join(run_dir, 'merged.csv'), index=False)
    
    thr = df_merged['err_p95_m'].quantile(HIGH_ERROR_QUANTILE)
    df_merged['high_error'] = (df_merged['err_p95_m'] >= thr).astype(int)
    print(f"High Error Threshold: {thr:.2f}m")
    
    features = [f for f in ['risk_proxy_5m', 'svf_proxy_5m', 'risk_cut5', 'hdop_cut_a_median', 'hdop_cut_b_median'] if f in df_merged.columns]
    
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
    
    # 簡易散布図
    if features:
        plt.figure(figsize=(15, 5))
        for i, f in enumerate(features[:3]):
            plt.subplot(1, 3, i+1)
            plt.scatter(df_merged[f], df_merged['err_p95_m'], alpha=0.6)
            plt.xlabel(f); plt.ylabel('Error p95 (m)')
        plt.tight_layout()
        plt.savefig(os.path.join(run_dir, 'plots', 'scatter_risk_err.png'))

    # Copy to latest
    for f in glob.glob(os.path.join(run_dir, '*')):
        if os.path.isfile(f): shutil.copy(f, latest_dir)
    if os.path.exists(os.path.join(latest_dir, 'plots')): shutil.rmtree(os.path.join(latest_dir, 'plots'))
    shutil.copytree(os.path.join(run_dir, 'plots'), os.path.join(latest_dir, 'plots'))
    print(f"\nCompleted. Results in: {latest_dir}")

if __name__ == "__main__":
    main()
