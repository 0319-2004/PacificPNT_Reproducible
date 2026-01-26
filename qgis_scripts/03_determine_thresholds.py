
exec(r"""
from qgis.core import QgsProject
import math

LAYER_NAME = "risk_proxy_5m"

layer = QgsProject.instance().mapLayersByName(LAYER_NAME)[0]
provider = layer.dataProvider()

block = provider.block(1, layer.extent(), layer.width(), layer.height())
nodata = provider.sourceNoDataValue(1)

values = []
for r in range(block.height()):
    for c in range(block.width()):
        v = block.value(c, r)
        if v is None:
            continue
        if nodata is not None and v == nodata:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        values.append(float(v))

if not values:
    raise RuntimeError("値が1つも取れませんでした")

values.sort()
n = len(values)

def quantile(p):
    # 0〜1 の p に対する補間付き分位点
    if p <= 0:
        return values[0]
    if p >= 1:
        return values[-1]
    k = (n - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    return values[f] + (values[c] - values[f]) * (k - f)

print("n:", n)
print("min:", values[0], "max:", values[-1])
for p in (0.30, 0.50, 0.70):
    print(f"q{int(p*100)}:", quantile(p))
""")

