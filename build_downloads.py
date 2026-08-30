# -*- coding: utf-8 -*-
"""
生成 data/downloads.js：海康 DP/DS 型号的官网详情页链接 + 兜底产品列表页。
- 已知 2 个详情页 id（用户提供）；其余型号用兜底列表页。
- 官网是 JS 渲染 SPA，无法批量抓取详情 id / 彩页图纸直链，故采用「详情页(已知) + 列表页兜底」方案。
"""
import json, os

FALLBACK = "https://www.hikrobotics.com/cn/machinevision/visionproduct?typeId=357&id=384&pageNumber=1&pageSize=20&showEol=false"

DETAIL_MAP = {
    "MV-DP3060-01PS V2.0": "https://www.hikrobotics.com/cn/machinevision/productdetail/?id=14632",
    "MV-DP3120-01D V2.0": "https://www.hikrobotics.com/cn/machinevision/productdetail/?id=13349",
}

os.makedirs('data', exist_ok=True)
js = ('window.DOWNLOAD_FALLBACK=' + json.dumps(FALLBACK, ensure_ascii=False) + ';\n'
      'window.DOWNLOAD_MAP=' + json.dumps(DETAIL_MAP, ensure_ascii=False) + ';\n')
with open('data/downloads.js', 'w', encoding='utf-8') as f:
    f.write(js)
print(f'已生成 data/downloads.js ({os.path.getsize("data/downloads.js")} bytes)')
