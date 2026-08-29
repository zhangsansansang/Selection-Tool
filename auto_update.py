#!/usr/bin/env python3
"""
海康3D轮廓仪 — 竞品自动更新与对标脚本
=========================================
功能:
  1. 加载 index.html 中的 PRODUCT_DB 和 COMPETITOR_DB
  2. 接收新竞品型号 (JSON/CSV/命令行)
  3. 自动去重、对标、生成 COMPETITOR_DB 代码片段
  4. 可选: 直接更新 index.html

用法:
  python auto_update.py --from-json new_models.json          # 从JSON导入
  python auto_update.py --from-json new_models.json --apply   # 导入并更新index.html
  python auto_update.py --from-json new_models.json --dry-run # 仅预览差异
  python auto_update.py --single brand=Keyence series=LJ-X8000 model=LJ-X8050 xRange=25 zRepeat=0.3 zRange=10
"""

import re
import json
import sys
import os
import argparse
import shutil
from collections import defaultdict

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

# ============================================================
# 友商系列 → 海康系列映射表 (33个系列，从199条对标记录归纳)
# ============================================================
SERIES_MAP = {
    "Keyence": {
        "LJ-V7000": "DP3000",
        "LJ-X8000": "DP3000",
        "LJ-S8000": "5M",
    },
    "LMI": {
        "2100": "Unknown",
        "2300": "DP2000",
        "2400": "DP2000",
        "2500": "DP3000",
        "2600": "DP4000",
        "6300": "DP4000",
    },
    "Photon": {
        "GL7000": "DP2000",
        "GL8000": "DP4000",
        "GL9000": "DP4000",
    },
    "SSZN": {
        "SR5000": "DP2000",
        "SR7000": "DP2000",
        "SRI7000": "DP2000",
        "SR8000": "DP3000",
        "SRI8000": "DP3000",
        "SR9000": "DP4000",
        "SRI9000": "DP4000",
    },
    "Sick": {
        "Ruler3000": "DP3000",
    },
    "Huaray": {
        "DL3000": "DP2000",
        "DL3000高速": "DP3000",
        "DL5000": "DP3000",
        "DL5000高速": "DP4000",
    },
    "翌视": {
        "LVM2000": "DP2000",
        "LVM2300": "DP2000",
        "LVM2500": "DP3000",
        "LVM2700": "DP4000",
        "LVM3000": "DP2000",
        "LVM3300": "DP2000",
        "LVM3400": "DP3000",
        "LVM3500": "DP4000",
        "LVM3700": "DP4000",
        "LVM3900": "DP4000",
    },
    "Elsen": {
        "AT-S1000-04B": "DP2000",
        "AT-S1000-07B": "DP2000",
    },
    "Meca": {
        "LNX-8000": "DP4000",       # 梅卡曼德 Mech-Eye 4K线激光, 4096点/15kHz
        "LNX-7500": "DP3000",
    },
    "LMI": {
        "2100": "Unknown",
        "2300": "DP2000",
        "2400": "DP2000",
        "2500": "DP3000",
        "2600": "DP4000",
        "6300": "DP4000",
        "2700": "DP3000",       # 2025新系列, 3200点/20kHz
        "3500": "NotLineLaser", # 结构光快照式
        "4000": "NotLineLaser", # 线共焦
    },
    "OPT": {
        "LPE2": "DP2000",       # 标准款, 3200点/18kHz
        "LPD1": "DP2000",       # 入门款
        "LPD2": "DP4000",       # 进阶系列, 4096点/49kHz
        "LPF2": "DP4000",       # 进阶款, 3200点/0.2μm/18kHz
        "LPH2": "DP4000",       # 旗舰款, 6400点/54kHz/0.1μm
        "FPB1": "NotLineLaser", # 双投影条纹结构光
        "FPC1": "NotLineLaser", # 单投影条纹结构光
        "LSA1": "NotLineLaser", # 双目散斑结构光
    },
}

# ============================================================
# 数据加载
# ============================================================

def load_product_db(filepath):
    """从 index.html 解析 PRODUCT_DB"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    start = content.index("const PRODUCT_DB=[")
    end = content.index("];", start) + 2
    section = content[start:end]

    products = []
    for line in section.split("\n"):
        line = line.strip()
        if not line.startswith("{ model:"):
            continue
        entry = _parse_js_object(line)
        if entry:
            products.append(entry)
    return products


def load_competitor_db(filepath):
    """从 index.html 解析 COMPETITOR_DB"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    start = content.index("const COMPETITOR_DB=[")
    end = content.index("];", start) + 2
    section = content[start:end]

    competitors = []
    for line in section.split("\n"):
        line = line.strip()
        if not line.startswith("{ brand:"):
            continue
        entry = _parse_js_object(line)
        if entry:
            competitors.append(entry)
    return competitors


def _parse_js_object(line):
    """解析单行 JS 对象字面量"""
    entry = {}
    # Match all key:"value" or key:number pairs
    pattern = r'(\w+):("[^"]*"|\d+\.?\d*|true|false)'
    for m in re.finditer(pattern, line):
        key = m.group(1)
        val = m.group(2)
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val == "true":
            val = True
        elif val == "false":
            val = False
        else:
            try:
                val = float(val)
                if val == int(val):
                    val = int(val)
            except ValueError:
                pass
        entry[key] = val
    return entry if entry else None


# ============================================================
# 对标引擎
# ============================================================

def lookup_series(brand, comp_series):
    """查映射表获取海康系列"""
    brand_map = SERIES_MAP.get(brand, {})
    if comp_series in brand_map:
        return brand_map[comp_series]
    # 尝试部分匹配
    for known_series, hik_series in brand_map.items():
        if known_series in comp_series or comp_series in known_series:
            return hik_series
    return None


def infer_series(brand, comp_series):
    """按命名规律推断海康系列"""
    brand_map = SERIES_MAP.get(brand, {})
    if not brand_map:
        return None

    # 提取友商系列中的数字
    nums = re.findall(r"(\d+)", comp_series)
    if not nums:
        return None
    comp_num = int(nums[0])

    # 在同品牌已知系列中找数字最接近的
    best_series = None
    best_dist = float("inf")
    for known_series, hik_series in brand_map.items():
        known_nums = re.findall(r"(\d+)", known_series)
        if known_nums:
            dist = abs(int(known_nums[0]) - comp_num)
            if dist < best_dist:
                best_dist = dist
                best_series = hik_series

    return best_series


def match_competitor(product_db, brand, comp_series, xRange, zRepeat, zRange=None):
    """
    核心对标函数

    参数:
        product_db: 海康产品列表
        brand: 友商品牌 (英文)
        comp_series: 友商系列名
        xRange: 友商X轴视野 (mm)
        zRepeat: 友商Z重复精度 (μm)
        zRange: 友商Z景深 (mm), 可选

    返回:
        dict: {hikModel, hikSeries, confidence, xFar, zRepeat, warnings}
    """
    # Step 1: 确定海康系列
    hik_series = lookup_series(brand, comp_series)
    confidence = "high"

    if not hik_series:
        hik_series = infer_series(brand, comp_series)
        confidence = "medium" if hik_series else "low"

    if not hik_series or hik_series == "Unknown":
        return {
            "hikModel": "",
            "hikSeries": "Unknown",
            "confidence": "low",
            "xFar": None,
            "zRepeat": None,
            "warnings": [f"无法确定海康系列: brand={brand}, series={comp_series}"],
        }

    if hik_series == "NotLineLaser":
        return {
            "hikModel": "",
            "hikSeries": "NotLineLaser",
            "confidence": "high",
            "xFar": None,
            "zRepeat": None,
            "warnings": [f"非线激光产品(线共焦/结构光), 海康无线激光对标型号"],
        }

    # Step 2: 在目标系列中按 xFar 匹配
    candidates = [
        m
        for m in product_db
        if m.get("series") == hik_series and "-01P" in m.get("model", "")
    ]

    # 如果没有 -01P 型号（如 DP4000），放宽后缀限制
    if not candidates:
        candidates = [m for m in product_db if m.get("series") == hik_series]

    if not candidates:
        return {
            "hikModel": "",
            "hikSeries": hik_series,
            "confidence": "low",
            "xFar": None,
            "zRepeat": None,
            "warnings": [f"海康系列 {hik_series} 中无可用型号"],
        }

    # 按 xFar 接近度排序
    candidates.sort(key=lambda m: abs(m.get("xFar", 9999) - xRange))

    # 在 ±30% 范围内选最优
    close = [m for m in candidates if 0.7 <= m.get("xFar", 0) / xRange <= 1.3]
    best = close[0] if close else candidates[0]

    if not close:
        confidence = "medium"

    # Step 3: 精度校验
    warnings = []
    hik_zrepeat = best.get("zRepeat", 0)
    if hik_zrepeat > zRepeat * 2:
        warnings.append(
            f"[精度告警] 海康 zRepeat={hik_zrepeat}μm > 竞品 zRepeat={zRepeat}μm × 2"
        )
    if hik_zrepeat < zRepeat * 0.5:
        warnings.append(
            f"[过度对标] 海康 zRepeat={hik_zrepeat}μm << 竞品 zRepeat={zRepeat}μm，建议复核"
        )

    return {
        "hikModel": best["model"],
        "hikSeries": hik_series,
        "confidence": confidence,
        "xFar": best.get("xFar"),
        "zRepeat": hik_zrepeat,
        "zRange_hik": best.get("zRange"),
        "maxFreq": best.get("maxFreq"),
        "light": best.get("light", ""),
        "warnings": warnings,
    }


# ============================================================
# 去重
# ============================================================

def deduplicate(new_entries, existing_competitors):
    """按 brand+model 去重，返回仅包含新条目的列表"""
    existing_keys = {(c["brand"], c["model"]) for c in existing_competitors}
    fresh = []
    dupes = []
    for e in new_entries:
        if (e["brand"], e["model"]) in existing_keys:
            dupes.append(e)
        else:
            fresh.append(e)
    return fresh, dupes


# ============================================================
# 输出生成
# ============================================================

def gen_js_entry(entry):
    """生成单条 COMPETITOR_DB JS 代码"""
    parts = []
    parts.append(f'brand:"{entry["brand"]}"')
    parts.append(f'model:"{entry["model"]}"')
    parts.append(f'xRange:{entry.get("xRange", 0)}')
    parts.append(f'zRepeat:{entry.get("zRepeat", 0)}')
    parts.append(f'zRange:{entry.get("zRange", 0)}')
    parts.append(f'hikModel:"{entry["hikModel"]}"')
    parts.append(f'hikSeries:"{entry["hikSeries"]}"')
    if entry.get("xResolution"):
        parts.append(f'xResolution:"{entry["xResolution"]}"')
    if entry.get("scanRate"):
        parts.append(f'scanRate:"{entry["scanRate"]}"')
    if entry.get("note"):
        parts.append(f'note:"{entry["note"]}"')
    return "    { " + ", ".join(parts) + " },"


def gen_diff_report(fresh_entries, dupes, stats):
    """生成差异报告"""
    lines = []
    lines.append("# 竞品对标更新报告")
    lines.append(f"\n生成时间: {stats.get('date', 'N/A')}")
    lines.append(f"数据来源: {stats.get('source', 'N/A')}")
    lines.append(f"\n## 统计")
    lines.append(f"- 新条目: {len(fresh_entries)}")
    lines.append(f"- 重复跳过: {len(dupes)}")
    lines.append(f"- 高置信度: {sum(1 for e in fresh_entries if e.get('_confidence') == 'high')}")
    lines.append(f"- 中置信度: {sum(1 for e in fresh_entries if e.get('_confidence') == 'medium')}")
    lines.append(f"- 低置信度: {sum(1 for e in fresh_entries if e.get('_confidence') == 'low')}")

    if fresh_entries:
        lines.append(f"\n## 新增对标详情")
        for e in fresh_entries:
            conf_mark = {"high": "✅", "medium": "⚠️", "low": "❌"}.get(
                e.get("_confidence", ""), "?"
            )
            lines.append(f"\n### {conf_mark} {e['brand']} {e['model']} → {e['hikModel']}")
            lines.append(f"- 友商规格: xRange={e['xRange']}mm, zRepeat={e['zRepeat']}μm, zRange={e['zRange']}mm")
            lines.append(f"- 海康对标: {e['hikModel']} (系列={e['hikSeries']}, xFar={e.get('_hik_xFar')}mm, zRepeat={e.get('_hik_zRepeat')}μm)")
            lines.append(f"- 置信度: {e.get('_confidence', 'N/A')}")
            if e.get("_warnings"):
                for w in e["_warnings"]:
                    lines.append(f"- 告警: {w}")

    if dupes:
        lines.append(f"\n## 重复跳过 ({len(dupes)}条)")
        for e in dupes[:10]:
            lines.append(f"- {e['brand']} {e['model']} (已存在)")

    return "\n".join(lines)


def gen_js_block(fresh_entries):
    """生成可粘贴的 JS 代码块"""
    lines = ["// === 自动生成: 新增竞品对标条目 ==="]
    lines.append(f"// 共 {len(fresh_entries)} 条")
    for e in fresh_entries:
        lines.append(gen_js_entry(e))
    lines.append("// === 结束 ===")
    return "\n".join(lines)


# ============================================================
# index.html 更新
# ============================================================

def update_index_html(filepath, new_entries, backup=True):
    """在 index.html 的 COMPETITOR_DB 末尾追加新条目"""
    if backup:
        shutil.copy2(filepath, filepath + ".bak")
        print(f"[备份] {filepath}.bak")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 找到 COMPETITOR_DB 的最后一个 ]
    comp_start = content.index("const COMPETITOR_DB=[")
    comp_end = content.index("];", comp_start) + 2

    # 在 ]; 前插入新条目
    insert_lines = ""
    for e in new_entries:
        insert_lines += gen_js_entry(e) + "\n"

    new_content = content[: comp_end - 2] + "\n" + insert_lines + content[comp_end - 2 :]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[更新] 已添加 {len(new_entries)} 条到 COMPETITOR_DB")


# ============================================================
# 命令行接口
# ============================================================

def load_json_input(filepath):
    """加载 JSON 输入文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def main():
    parser = argparse.ArgumentParser(
        description="海康3D轮廓仪 — 竞品自动更新与对标"
    )
    parser.add_argument(
        "--index", default="index.html", help="index.html 路径 (默认: index.html)"
    )
    parser.add_argument(
        "--from-json", help="从 JSON 文件加载新竞品数据"
    )
    parser.add_argument(
        "--single", help="单个竞品对标: brand=X series=Y model=Z xRange=N zRepeat=M zRange=K"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="仅预览差异，不修改文件"
    )
    parser.add_argument(
        "--apply", action="store_true", help="直接更新 index.html"
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="更新时不备份原文件"
    )
    parser.add_argument(
        "--output-js", help="输出 JS 代码片段到指定文件"
    )
    parser.add_argument(
        "--output-report", help="输出差异报告到指定文件"
    )
    args = parser.parse_args()

    # 加载数据库
    print(f"[加载] PRODUCT_DB + COMPETITOR_DB from {args.index}")
    if not os.path.exists(args.index):
        print(f"错误: 找不到 {args.index}")
        sys.exit(1)

    product_db = load_product_db(args.index)
    competitor_db = load_competitor_db(args.index)
    print(f"  PRODUCT_DB: {len(product_db)} 款")
    print(f"  COMPETITOR_DB: {len(competitor_db)} 条")

    # 准备输入条目
    new_input = []

    if args.single:
        # 解析 --single 参数 (支持引号包裹含空格的值)
        entry = {"brand": "", "series": "", "model": "", "xRange": 0, "zRepeat": 0, "zRange": 0}
        # 使用 shlex 风格解析，处理 "key=value with spaces" 格式
        import shlex
        tokens = shlex.split(args.single)
        for token in tokens:
            if "=" not in token:
                continue
            k, v = token.split("=", 1)
            if k in ("xRange", "zRepeat", "zRange"):
                v = float(v)
            entry[k] = v
        new_input = [entry]

    elif args.from_json:
        data = load_json_input(args.from_json)
        if isinstance(data, list):
            new_input = data
        elif isinstance(data, dict) and "entries" in data:
            new_input = data["entries"]
        else:
            print("错误: JSON 格式不正确，需要数组或包含 'entries' 键的对象")
            sys.exit(1)

    else:
        parser.print_help()
        print("\n示例:")
        print("  python auto_update.py --single 'brand=Keyence series=LJ-X8000 model=LJ-X8050 xRange=25 zRepeat=0.3 zRange=10'")
        print("  python auto_update.py --from-json new_models.json --dry-run")
        print("  python auto_update.py --from-json new_models.json --apply")
        sys.exit(0)

    # 去重
    fresh, dupes = deduplicate(new_input, competitor_db)
    print(f"\n[去重] 输入 {len(new_input)} 条 → 新增 {len(fresh)} 条, 重复 {len(dupes)} 条")

    if dupes:
        for d in dupes:
            print(f"  跳过: {d['brand']} {d['model']} (已存在)")

    if not fresh:
        print("\n没有新条目，无需更新。")
        return

    # 对标
    print(f"\n[对标] 为 {len(fresh)} 条新竞品匹配海康型号...")
    for entry in fresh:
        result = match_competitor(
            product_db,
            entry.get("brand", ""),
            entry.get("series", ""),
            entry.get("xRange", 0),
            entry.get("zRepeat", 0),
            entry.get("zRange"),
        )
        entry["hikModel"] = result["hikModel"]
        entry["hikSeries"] = result["hikSeries"]
        entry["_confidence"] = result["confidence"]
        entry["_hik_xFar"] = result.get("xFar")
        entry["_hik_zRepeat"] = result.get("zRepeat")
        entry["_warnings"] = result.get("warnings", [])

        conf_label = {"high": "[HIGH]", "medium": "[MED ]", "low": "[LOW ]"}.get(result["confidence"], "[????]")
        print(f"  {conf_label} {entry['brand']:8s} {entry['model']:20s} -> {result['hikModel']:25s} [{result['confidence']}]")
        for w in result.get("warnings", []):
            print(f"     {w}")

    # 输出
    js_block = gen_js_block(fresh)
    report = gen_diff_report(fresh, dupes, {"date": "auto", "source": args.from_json or "cli"})

    if args.output_js:
        with open(args.output_js, "w", encoding="utf-8") as f:
            f.write(js_block)
        print(f"\n[JS输出] {args.output_js}")

    if args.output_report:
        with open(args.output_report, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[报告] {args.output_report}")

    if args.dry_run:
        print("\n===== 预览: JS 代码片段 =====")
        print(js_block)
        print("\n===== 预览: 差异报告 =====")
        print(report)
        print("\n[DRY RUN] 未修改 index.html。使用 --apply 实际应用更改。")
    elif args.apply:
        # 清理辅助字段后写入
        clean_entries = []
        for e in fresh:
            clean = {
                k: v
                for k, v in e.items()
                if not k.startswith("_")
            }
            clean_entries.append(clean)
        update_index_html(args.index, clean_entries, backup=not args.no_backup)
        print(f"\n[完成] 已更新 {args.index}，新增 {len(fresh)} 条对标记录")
    else:
        print("\n===== JS 代码片段 (可复制粘贴到 COMPETITOR_DB) =====")
        print(js_block)
        print("\n===== 差异报告 =====")
        print(report)
        print("\n提示: 使用 --apply 自动更新 index.html, 或 --dry-run 仅预览")


if __name__ == "__main__":
    main()
