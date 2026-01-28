import os
import csv
import argparse

# ================= CONSTANTS =================
FIX_PREFIX = "Fix,"
STATUS_PREFIX = "Status,"
RAW_PREFIX = "Raw,"

# Fix has 17 columns total
FIX_COLS_17 = [
    "Fix",
    "Provider",            # idx 1
    "Latitude",            # idx 2
    "Longitude",           # idx 3
    "AltMeters",           # idx 4
    "SpeedMps",            # idx 5
    "Accuracy",            # idx 6
    "BearingDeg",          # idx 7
    "UnixTimeMillis",      # idx 8
    "SpeedAccMps",         # idx 9
    "BearingAccDeg",       # idx 10
    "TimeNanos",           # idx 11
    "Col12", "Col13", "Col14", "Col15", "Col16"
]

# Status has 14 columns total
STATUS_COLS_14 = [
    "Status",
    "UnixTimeMillis",      # idx 1
    "Svid",                # idx 2
    "ConstellationType",   # idx 3
    "Col4",
    "AzimuthDegrees",      # idx 5
    "CarrierFrequencyHz",  # idx 6
    "Cn0DbHz",             # idx 7
    "Col8",
    "ElevationDegrees",    # idx 9
    "UsedInFix",           # idx 10
    "HasAlmanacData",      # idx 11
    "HasEphemerisData",    # idx 12
    "Col13"
]

# Raw has 36 columns total
RAW_COLS_36 = [
    "Raw", "TimeNanos", "FullBiasNanos", "BiasNanos", "BiasUncertaintyNanos",
    "DriftNanosPerSecond", "DriftUncertaintyNanosPerSecond",
    "HardwareClockDiscontinuityCount", "Svid", "TimeOffsetNanos", "State",
    "ReceivedSvTimeNanos", "ReceivedSvTimeUncertaintyNanos", "Cn0DbHz",
    "PseudorangeRateMetersPerSecond", "PseudorangeRateUncertaintyMetersPerSecond",
    "AccumulatedDeltaRangeState", "AccumulatedDeltaRangeMeters",
    "AccumulatedDeltaRangeUncertaintyMeters", "CarrierFrequencyHz", "CarrierCycles",
    "CarrierPhase", "CarrierPhaseUncertainty", "MultipathIndicator", "SnrInDb",
    "ConstellationType", "AgcDb", "BasebandCn0DbHz",
    "Col28", "Col29", "Col30", "Col31", "Col32", "Col33", "Col34", "Col35"
]

def count_cols(line: str) -> int:
    return len(next(csv.reader([line])))

def has_header(lines, rec_type: str) -> bool:
    parsed = [next(csv.reader([ln])) for ln in lines]
    for row in parsed:
        if len(row) < 2:
            continue
        second = (row[1] or "").strip()
        if rec_type == "Fix" and second in ("Provider", "Latitude", "Longitude", "UnixTimeMillis", "TimeNanos"):
            return True
        if rec_type == "Status" and second in ("UnixTimeMillis", "TimeNanos", "Svid", "Cn0DbHz", "ElevationDegrees", "UsedInFix"):
            return True
        if rec_type == "Raw" and second in ("TimeNanos", "FullBiasNanos", "Svid", "Cn0DbHz"):
            return True
    return False

def normalize_gnss_headers(in_dir, out_dir, no_raw_header=False):
    """
    GNSS Logger形式のテキストファイルを読み込み、ヘッダーが欠落している場合に補完して出力する。
    """
    print("=========== GNSS HEADER NORMALIZATION START ===========")
    
    # 出力ディレクトリ作成
    if not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
        print(f"[*] ディレクトリを作成しました: {out_dir}")

    # 入力ディレクトリ確認
    if not os.path.exists(in_dir):
        raise FileNotFoundError(f"入力ディレクトリが見つかりません: {in_dir}")

    files = [f for f in os.listdir(in_dir) if f.lower().endswith(".txt")]
    files.sort()

    if not files:
        print(f"[!] {in_dir} に .txt ファイルが見つかりません。")
        return

    for fname in files:
        src_path = os.path.join(in_dir, fname)
        dst_path = os.path.join(out_dir, fname)

        # ファイル読み込み
        with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()

        fix_lines = [ln for ln in lines if ln.startswith(FIX_PREFIX)]
        status_lines = [ln for ln in lines if ln.startswith(STATUS_PREFIX)]
        raw_lines = [ln for ln in lines if ln.startswith(RAW_PREFIX)]

        need_fix_header = bool(fix_lines) and (not has_header(fix_lines[:200], "Fix"))
        need_status_header = bool(status_lines) and (not has_header(status_lines[:200], "Status"))
        need_raw_header = (not no_raw_header) and bool(raw_lines) and (not has_header(raw_lines[:200], "Raw"))

        # Sanity check
        if need_fix_header:
            n = count_cols(fix_lines[0])
            if n != len(FIX_COLS_17):
                raise RuntimeError(f"{fname}: Fix cols={n} but expected {len(FIX_COLS_17)}.")
        if need_status_header:
            n = count_cols(status_lines[0])
            if n != len(STATUS_COLS_14):
                raise RuntimeError(f"{fname}: Status cols={n} but expected {len(STATUS_COLS_14)}.")
        if need_raw_header:
            n = count_cols(raw_lines[0])
            if n != len(RAW_COLS_36):
                raise RuntimeError(f"{fname}: Raw cols={n} but expected {len(RAW_COLS_36)}.")

        seen_fix = False
        seen_status = False
        seen_raw = False

        out_lines = []
        for ln in lines:
            # Header insertion
            if (not seen_fix) and need_fix_header and ln.startswith(FIX_PREFIX):
                out_lines.append(",".join(FIX_COLS_17))
                seen_fix = True
            if (not seen_status) and need_status_header and ln.startswith(STATUS_PREFIX):
                out_lines.append(",".join(STATUS_COLS_14))
                seen_status = True
            if (not seen_raw) and need_raw_header and ln.startswith(RAW_PREFIX):
                out_lines.append(",".join(RAW_COLS_36))
                seen_raw = True

            out_lines.append(ln)

            # Mark as seen
            if (not seen_fix) and ln.startswith(FIX_PREFIX):
                seen_fix = True
            if (not seen_status) and ln.startswith(STATUS_PREFIX):
                seen_status = True
            if (not seen_raw) and ln.startswith(RAW_PREFIX):
                seen_raw = True

        with open(dst_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines) + "\n")
        
        print(f"[OK] Normalized: {fname}")

    print("=========== GNSS HEADER NORMALIZATION DONE ===========")


if __name__ == "__main__":
    # ファイル配置場所: src/00_utils/ (Rootから2階層深い)
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # デフォルト設定:
    # 入力: ../../data/raw (生のGNSSログ置き場と想定)
    # 出力: ../../data/processed/gnss_normalized (整形済みログ置き場)
    default_in_dir = os.path.join(base_dir, "..", "..", "data", "raw")
    default_out_dir = os.path.join(base_dir, "..", "..", "data", "processed", "gnss_normalized")

    # 引数処理 (手動オーバーライド可能にする)
    parser = argparse.ArgumentParser()
    parser.add_argument("--in_dir", default=default_in_dir, help="Input directory containing raw .txt")
    parser.add_argument("--out_dir", default=default_out_dir, help="Output directory for normalized .txt")
    parser.add_argument("--no_raw_header", action="store_true", help="Disable Raw header insertion")
    args = parser.parse_args()

    normalize_gnss_headers(args.in_dir, args.out_dir, args.no_raw_header)
