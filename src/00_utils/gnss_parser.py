# normalize_gnsslogger_txt_headers.py
import argparse
import csv
from pathlib import Path

FIX_PREFIX = "Fix,"
STATUS_PREFIX = "Status,"
RAW_PREFIX = "Raw,"

# Your sample file suggests:
# Fix has 17 columns total, Status has 14 columns total.
FIX_COLS_17 = [
    "Fix",
    "Provider",            # idx 1
    "Latitude",            # idx 2
    "Longitude",           # idx 3
    "AltMeters",           # idx 4 (placeholder)
    "SpeedMps",            # idx 5 (placeholder)
    "Accuracy",            # idx 6
    "BearingDeg",          # idx 7 (often blank)
    "UnixTimeMillis",      # idx 8
    "SpeedAccMps",         # idx 9 (placeholder)
    "BearingAccDeg",       # idx 10 (often blank)
    "TimeNanos",           # idx 11
    "Col12",               # idx 12 (placeholder)
    "Col13",               # idx 13 (placeholder)
    "Col14",               # idx 14 (placeholder)
    "Col15",               # idx 15 (placeholder)
    "Col16",               # idx 16 (placeholder)
]

# Status mapping inferred from your sample:
# idx 1: UnixTimeMillis (sometimes blank)
# idx 2: Svid (8..13 etc.)
# idx 7: Cn0DbHz (11..30 range)
# idx 9: ElevationDegrees (30..85 range)
# idx 10: UsedInFix (0/1)
STATUS_COLS_14 = [
    "Status",
    "UnixTimeMillis",      # idx 1
    "Svid",                # idx 2
    "ConstellationType",   # idx 3 (placeholder)
    "Col4",                # idx 4 (placeholder)
    "AzimuthDegrees",      # idx 5 (placeholder)
    "CarrierFrequencyHz",  # idx 6 (placeholder)
    "Cn0DbHz",             # idx 7
    "Col8",                # idx 8 (placeholder)
    "ElevationDegrees",    # idx 9
    "UsedInFix",           # idx 10
    "HasAlmanacData",      # idx 11 (placeholder)
    "HasEphemerisData",    # idx 12 (placeholder)
    "Col13",               # idx 13 (placeholder)
]

# Optional: only if you want Raw header insertion.
# If your Raw column count differs, you can disable Raw insertion via --no_raw_header
RAW_COLS_36 = [
    "Raw",
    "TimeNanos",
    "FullBiasNanos",
    "BiasNanos",
    "BiasUncertaintyNanos",
    "DriftNanosPerSecond",
    "DriftUncertaintyNanosPerSecond",
    "HardwareClockDiscontinuityCount",
    "Svid",
    "TimeOffsetNanos",
    "State",
    "ReceivedSvTimeNanos",
    "ReceivedSvTimeUncertaintyNanos",
    "Cn0DbHz",
    "PseudorangeRateMetersPerSecond",
    "PseudorangeRateUncertaintyMetersPerSecond",
    "AccumulatedDeltaRangeState",
    "AccumulatedDeltaRangeMeters",
    "AccumulatedDeltaRangeUncertaintyMeters",
    "CarrierFrequencyHz",
    "CarrierCycles",
    "CarrierPhase",
    "CarrierPhaseUncertainty",
    "MultipathIndicator",
    "SnrInDb",
    "ConstellationType",
    "AgcDb",
    "BasebandCn0DbHz",
    "Col28",
    "Col29",
    "Col30",
    "Col31",
    "Col32",
    "Col33",
    "Col34",
    "Col35",
]

def count_cols(line: str) -> int:
    return len(next(csv.reader([line])))

def has_header(lines, rec_type: str) -> bool:
    # Matches your pipeline's heuristic: second field equals known header tokens
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", required=True, help="Directory containing original GNSS Logger .txt")
    ap.add_argument("--out_dir", required=True, help="Directory to write normalized .txt for your pipeline logs/")
    ap.add_argument("--no_raw_header", action="store_true", help="Disable Raw header insertion")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for src in sorted(in_dir.glob("*.txt")):
        lines = src.read_text(encoding="utf-8", errors="ignore").splitlines()

        fix_lines = [ln for ln in lines if ln.startswith(FIX_PREFIX)]
        status_lines = [ln for ln in lines if ln.startswith(STATUS_PREFIX)]
        raw_lines = [ln for ln in lines if ln.startswith(RAW_PREFIX)]

        need_fix_header = bool(fix_lines) and (not has_header(fix_lines[:200], "Fix"))
        need_status_header = bool(status_lines) and (not has_header(status_lines[:200], "Status"))
        need_raw_header = (not args.no_raw_header) and bool(raw_lines) and (not has_header(raw_lines[:200], "Raw"))

        # Sanity check: ensure column counts match what we are about to insert
        if need_fix_header:
            n = count_cols(fix_lines[0])
            if n != len(FIX_COLS_17):
                raise RuntimeError(f"{src.name}: Fix cols={n} but expected {len(FIX_COLS_17)}. Please update FIX_COLS list.")
        if need_status_header:
            n = count_cols(status_lines[0])
            if n != len(STATUS_COLS_14):
                raise RuntimeError(f"{src.name}: Status cols={n} but expected {len(STATUS_COLS_14)}. Please update STATUS_COLS list.")
        if need_raw_header:
            n = count_cols(raw_lines[0])
            if n != len(RAW_COLS_36):
                # Raw is not used in your pipeline; allow mismatch only if you prefer.
                # Here we hard-fail to keep strict reproducibility.
                raise RuntimeError(f"{src.name}: Raw cols={n} but expected {len(RAW_COLS_36)}. Use --no_raw_header or update RAW_COLS list.")

        seen_fix = False
        seen_status = False
        seen_raw = False

        out_lines = []
        for ln in lines:
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

            # Mark as seen even if we did not need header
            if (not seen_fix) and ln.startswith(FIX_PREFIX):
                seen_fix = True
            if (not seen_status) and ln.startswith(STATUS_PREFIX):
                seen_status = True
            if (not seen_raw) and ln.startswith(RAW_PREFIX):
                seen_raw = True

        dst = out_dir / src.name
        dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    print("OK: normalized txt written to", out_dir)

if __name__ == "__main__":
    main()
