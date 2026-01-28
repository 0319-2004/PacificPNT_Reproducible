import os

print("=========== AREA SUMMARY START ===========")

# ---- 0. パス設定 (相対パス化) ----
# このスクリプトではファイル出力はありませんが、
# プロジェクト全体の方針に合わせてパス定義を追加しておきます。
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, "data", "processed")

# 出力先フォルダの自動生成（念のため）
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

# 5m解像度の class raster の面積サマリ（counts→m²→割合）
# ※countsは直前の解析結果に基づいて入力してください
counts = {1: 2888, 2: 3850, 3: 2888}
pix = 5
area_per_pix = pix * pix  # 25 m^2

total = sum(counts.values())

print(f"▶ 基準ディレクトリ: {BASE_DIR}")
print("pixel_size(m):", pix)
print("valid_pixels:", total)
print("valid_area_m2:", total * area_per_pix)

labels = {1: "open", 2: "street", 3: "alley"}
print("\n--- Classification Result ---")
for k in sorted(counts):
    a = counts[k] * area_per_pix
    p = counts[k] / total * 100
    print(f"{k} {labels[k]}: pixels={counts[k]} area_m2={a} share={p:.2f}%")

print("=========== AREA SUMMARY DONE ===========")
