exec("""
# 5m解像度の class raster の面積サマリ（counts→m²→割合）
counts = {1: 2888, 2: 3850, 3: 2888}  # さっき出た値
pix = 5
area_per_pix = pix * pix  # 25 m^2

total = sum(counts.values())
print("pixel_size(m):", pix)
print("valid_pixels:", total)
print("valid_area_m2:", total * area_per_pix)

labels = {1:"open", 2:"street", 3:"alley"}
for k in sorted(counts):
    a = counts[k] * area_per_pix
    p = counts[k] / total * 100
    print(f"{k} {labels[k]}: pixels={counts[k]} area_m2={a} share={p:.2f}%")
""")

