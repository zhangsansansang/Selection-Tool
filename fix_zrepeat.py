# -*- coding: utf-8 -*-
import re

# 官方 Z轴重复精度 (μm, @光学平台标准量块) — DP3000/DP4000 为官方值, DP2000 按同光路平行推断
CORRECT = {
    # DP2000 (平行于 DP3000, 同光路推断)
    "MV-DP2020-01P V2.0": 0.22, "MV-DP2023-01P V2.0": 0.27, "MV-DP2050-01P V2.0": 0.41,
    "MV-DP2060-01P V2.0": 0.56, "MV-DP2060-03P V2.0": 0.56, "MV-DP2061-01P V2.0": 0.33,
    "MV-DP2062-01P V2.0": 0.30, "MV-DP2080-01P V2.0": 1.03, "MV-DP2120-01P V2.0": 1.68,
    "MV-DP2120-03P V2.0": 1.68, "MV-DP2140-01P V2.0": 1.73, "MV-DP2240-01P V2.0": 2.20,
    "MV-DP2240-03P V2.0": 2.20, "MV-DP2300-01P V2.0": 4.45, "MV-DP2300-03P V2.0": 4.45,
    "MV-DP2470-01P V2.0": 4.84, "MV-DP2470-03P V2.0": 4.84, "MV-DP2580-01P V2.0": 4.84,
    "MV-DP2580-03P V2.0": 4.84, "MV-DP2900-03P V2.0": 8.12,
    # DP3000 (官方)
    "MV-DP3020-01P V2.0": 0.22, "MV-DP3023-01P V2.0": 0.27, "MV-DP3050-01P V2.0": 0.41,
    "MV-DP3060-01P V2.0": 0.56, "MV-DP3060-03P V2.0": 0.56, "MV-DP3061-01P V2.0": 0.33,
    "MV-DP3062-01P V2.0": 0.30, "MV-DP3080-01P V2.0": 1.03, "MV-DP3120-01P V2.0": 1.68,
    "MV-DP3120-03P V2.0": 1.68, "MV-DP3140-01P V2.0": 1.73, "MV-DP3240-01P V2.0": 2.20,
    "MV-DP3240-03P V2.0": 2.20, "MV-DP3300-01P V2.0": 4.45, "MV-DP3300-03P V2.0": 4.45,
    "MV-DP3470-01P V2.0": 4.84, "MV-DP3470-03P V2.0": 4.84, "MV-DP3580-01P V2.0": 4.84,
    "MV-DP3580-03P V2.0": 4.84, "MV-DP3900-03P V2.0": 8.12,
    "MV-DP2060-01D V2.0": 0.49, "MV-DP2120-01D V2.0": 1.68, "MV-DP3060-01D V2.0": 0.49,
    "MV-DP3062-01D V2.0": 0.30, "MV-DP3120-01D V2.0": 1.68,
    # DP4000 (官方)
    "MV-DP4020-01P": 0.15, "MV-DP4060-01P": 0.36, "MV-DP4090-01P": 0.66,
    "MV-DP4180-01P": 1.50, "MV-DP4180-03P": 1.50, "MV-DP4430-01P": 2.27,
    "MV-DP4430-03P": 2.27, "MV-DP4940-03P": 9.45,
}

with open("index.html", encoding="utf-8") as f:
    lines = f.readlines()

changed = 0
for i, line in enumerate(lines):
    m = re.search(r'model:"([^"]+)"', line)
    if not m or m.group(1) not in CORRECT:
        continue
    v = CORRECT[m.group(1)]
    vs = f"{v:.2f}"
    newline = line
    newline = re.sub(r'zRepeat:\d+\.?\d*', f'zRepeat:{vs}', newline, count=1)
    newline = re.sub(r'zRepeatMax:\d+\.?\d*', f'zRepeatMax:{vs}', newline, count=1)
    newline = re.sub(r'zRepeatDisplay:"[^"]*"', f'zRepeatDisplay:"{vs}"', newline, count=1)
    if newline != line:
        lines[i] = newline
        changed += 1

with open("index.html", "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"已修正 {changed} 个型号的 Z轴重复精度")
