#!/usr/bin/env python3
"""
海康3D轮廓仪 — 全自动竞品监控与更新系统 v2
============================================
基于实测验证的多策略架构:
  策略1 (主): 直接 HTTP 抓取产品页面 (GitHub Actions 云环境效果最好)
  策略2 (辅): DuckDuckGo 搜索引擎发现 (本地/防火墙后可用)
  策略3 (AI): 接受 Claude WebSearch 结果 JSON, 自动对标

每15天 GitHub Actions 自动运行, 零人工介入.

用法:
  python auto_scraper.py                         # 全品牌监控预览
  python auto_scraper.py --brand SSZN            # 单品牌
  python auto_scraper.py --apply                 # 实际更新 index.html
  python auto_scraper.py --apply --push          # 更新 + 自动 git push
  python auto_scraper.py --from-search result.json  # 从Claude搜索结果导入
"""

import re
import json
import sys
import os
import shutil
import subprocess
import argparse
from datetime import datetime
from collections import defaultdict
from urllib.parse import quote_plus

# UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ============================================================
# 对标引擎导入
# ============================================================

from auto_update import (
    load_product_db,
    load_competitor_db,
    match_competitor,
    deduplicate,
    gen_js_entry,
    SERIES_MAP,
)

# ============================================================
# 配置: 每个品牌的发现策略
# ============================================================

COMPETITOR_CONFIG = {
    "Keyence": {
        # 直接抓取的产品页面 (GitHub Actions 云环境可用)
        "product_pages": [
            "https://www.keyence.com.cn/products/measure/laser-2d/lj-x8000/models/",
            "https://www.keyence.com.cn/products/measure/laser-2d/lj-v7000/models/",
            "https://www.keyence.com/products/measure/laser-profiler/lj-s8000/models/",
        ],
        # DuckDuckGo 搜索查询 (本地/防火墙后可用)
        "search_queries": [
            "Keyence LJ-X8000 LJ-V7000 激光轮廓仪 型号 参数 X轴视野 Z重复精度 site:keyence.com.cn",
            "Keyence LJ-S8000 结构光 新型号 图像分辨率 2025 2026",
        ],
        "model_pattern": r"LJ-[VSX]\d{4}",
    },
    "LMI": {
        "product_pages": [
            "https://lmi3d.com/3d-smart-sensors/",
        ],
        "search_queries": [
            "LMI Gocator 3D smart sensor specifications FOV Z repeatability series 2600 2500 2400",
            "LMI Gocator G2 G3 new model 2025 2026 laser profiler",
        ],
        "model_pattern": r"G\d{4}",
    },
    "SSZN": {
        "product_pages": [
            "https://www.cnsszn.com/industrial-sensors/3d-laser-profiler",
            "https://www.cnsszn.com.cn/industrial-sensors/3d-laser-profiler/sri-series",
            "https://www.cnsszn.com.cn/industrial-sensors/3d-laser-profiler/sr-series",
        ],
        "search_queries": [
            "深视智能 SSZN 3D线激光轮廓仪 SR SRI 新型号 X轴宽度 Z重复精度 2025 2026",
            "深视智能 SRI9022 SRI9000 三维激光轮廓测量仪 参数 规格",
        ],
        "model_pattern": r"SR[IA]?\d{4}[A-Za-z]?",
    },
    "Photon": {
        "product_pages": [],
        "search_queries": [
            "光子 Photon GL8000 GL9000 3D线激光轮廓仪 型号 参数 X轴视野 Z重复精度",
            "Photon 3D laser profiler GL series specifications 2025",
        ],
        "model_pattern": r"GL-\d{3,5}",
    },
    "Sick": {
        "product_pages": [],
        "search_queries": [
            "Sick Ruler3000 Ruler 3D相机 型号 X轴视野 Z重复精度 参数",
            "Sick Ruler 3D streaming camera new model 2025 2026",
        ],
        "model_pattern": r"Ruler\d{4}",
    },
    "Huaray": {
        "product_pages": [],
        "search_queries": [
            "华睿 Huaray DL3000 DL5000 3D线激光轮廓仪 型号 参数 2025",
            "华睿 3D轮廓仪 DL系列 X轴视野 Z重复精度",
        ],
        "model_pattern": r"DL\d{4}[A-Za-z]?(?:-[A-Za-z]+)?",
    },
    "翌视": {
        "product_pages": [],
        "search_queries": [
            "翌视 LVM2000 LVM3000 LVM3400 3D线激光轮廓仪 型号 参数 2025",
            "翌视科技 3D激光轮廓传感器 X轴 Z重复精度 新型号",
        ],
        "model_pattern": r"LVM\d{4}",
    },
    "Elsen": {
        "product_pages": [],
        "search_queries": [
            "埃尔森 Elsen AT-S1000 3D线激光轮廓仪 型号 参数",
            "埃尔森 3D激光轮廓传感器 AT系列 新型号 2025",
        ],
        "model_pattern": r"AT-S\d{4}-\d{2}[A-Za-z]-S?\d+",
    },
    "OPT": {
        "product_pages": [
            "https://www.optmv.com/content/details185_357595.html",
        ],
        "search_queries": [
            "OPT 奥普特 全系列 3D相机 线激光 LPE LPF LPH LPD 结构光 FPB FPC LSA 2025",
            "OPT optmv.com LPE2 LPF2 LPH2 LPD2 线激光轮廓仪 型号 参数 X轴 Z精度",
            "OPT FPB1 FPC1 LSA1 3D结构光相机 型号 视野 Z精度",
        ],
        "model_pattern": r"OPT-[A-Z]{2,4}\d?-\d{2,4}(?:-\d{2})?",
    },
    "Meca": {
        "product_pages": [],
        "search_queries": [
            "梅卡 Meca LNX 3D线激光轮廓仪 型号 参数",
            "Meca 3D laser profiler LNX series specifications",
        ],
        "model_pattern": r"LNX-\d{4,5}",
    },
}

# ============================================================
# 策略1: 直接 HTTP 抓取
# ============================================================

def fetch_page(url, timeout=8):
    """尝试直接抓取页面 HTML"""
    try:
        import urllib.request
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def extract_models(html, brand_config):
    """从 HTML 文本中提取型号"""
    if not html:
        return []
    pattern = brand_config.get("model_pattern", r"[A-Z]+-\d{3,5}")
    blacklist = {"html", "http", "https", "www", "css", "js", "gif",
                 "png", "jpg", "xml", "pdf", "php", "asp"}
    matches = set(re.findall(pattern, html, re.IGNORECASE))
    return [m for m in matches if m.lower() not in blacklist and len(m) >= 4]


def direct_fetch_strategy(brand, brand_config, existing_models):
    """策略1: 直接抓取产品页面"""
    found = []
    for url in brand_config.get("product_pages", []):
        html = fetch_page(url)
        if html:
            models = extract_models(html, brand_config)
            new_models = [m for m in models if m not in existing_models]
            for m in new_models:
                found.append({
                    "brand": brand, "model": m,
                    "source": url, "method": "direct_fetch",
                })
    return found


# ============================================================
# 策略2: DuckDuckGo 搜索引擎发现
# ============================================================

def duckduckgo_search_strategy(brand, brand_config, existing_models):
    """策略2: 通过 DuckDuckGo HTML 搜索发现新型号"""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    found = []
    for query in brand_config.get("search_queries", []):
        try:
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            resp = requests.get(
                search_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            # 提取搜索结果摘要文本
            snippets = []
            for s in soup.select(".result__snippet"):
                snippets.append(s.get_text())
            text = " ".join(snippets)

            # 用正则提取型号
            pattern = brand_config.get("model_pattern", r"[A-Z]+-\d+")
            models = set(re.findall(pattern, text, re.IGNORECASE))
            new_models = [m for m in models if m not in existing_models and len(m) >= 4]
            for m in new_models:
                found.append({
                    "brand": brand, "model": m,
                    "source": f"search:{query[:30]}",
                    "method": "search_engine",
                })
        except Exception:
            continue

    return found


# ============================================================
# 策略3: Claude WebSearch 结果导入
# ============================================================

def load_search_results_json(filepath):
    """加载 Claude WebSearch 导出的 JSON 结果"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 规格推断 (从型号名 + 已知参数推测)
# ============================================================

def infer_specs(brand, model, brand_config):
    """仅有型号名时, 尝试推断系列名"""
    for known_series in SERIES_MAP.get(brand, {}):
        if known_series.lower() in model.lower():
            return {"series": known_series}

    # 按命名规律: 提取数字, 在同品牌中找最接近的系列
    nums = re.findall(r"(\d{3,4})", model)
    if nums:
        model_num = int(nums[0])
        best, best_dist = None, float("inf")
        for s in SERIES_MAP.get(brand, {}):
            sn = re.findall(r"(\d{3,4})", s)
            if sn:
                dist = abs(int(sn[0]) - model_num)
                if dist < best_dist:
                    best_dist = dist
                    best = s
        return {"series": best} if best else {}
    return {}


# ============================================================
# 主监控流程
# ============================================================

def run_monitor_cycle(
    index_path="index.html",
    brands=None,
    dry_run=True,
    push=False,
    skip_network=False,
    from_search_file=None,
):
    """完整监控周期"""
    report = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report.append(f"# 轮廓仪竞品自动监控报告\n运行时间: {now}\n")

    # 加载数据
    product_db = load_product_db(index_path)
    competitor_db = load_competitor_db(index_path)
    existing_keys = {(c["brand"], c["model"]) for c in competitor_db}

    report.append(f"## 基线\n- 海康: {len(product_db)} 款 | 竞品: {len(competitor_db)} 条\n")

    target_brands = brands or list(COMPETITOR_CONFIG.keys())
    all_discovered = []

    for brand in target_brands:
        config = COMPETITOR_CONFIG.get(brand, {})
        if not config:
            continue

        existing_brand = {m for b, m in existing_keys if b == brand}
        report.append(f"### {brand}")

        brand_discovered = []

        # 策略1: 直接抓取
        if not skip_network:
            try:
                results = direct_fetch_strategy(brand, config, existing_brand)
                brand_discovered.extend(results)
                if results:
                    report.append(f"  - 直接抓取: 发现 {len(results)} 个潜在新型号")
            except Exception as e:
                report.append(f"  - 直接抓取: 失败 ({e})")

        # 策略2: 搜索引擎
        if not skip_network:
            try:
                results = duckduckgo_search_strategy(brand, config, existing_brand)
                # 去重 (同品牌内)
                existing_found = {d["model"] for d in brand_discovered}
                new_unique = [r for r in results if r["model"] not in existing_found]
                brand_discovered.extend(new_unique)
                if new_unique:
                    report.append(f"  - 搜索引擎: 发现 {len(new_unique)} 个潜在新型号")
            except Exception as e:
                report.append(f"  - 搜索引擎: 失败 ({e})")

        if skip_network:
            report.append(f"  - 已跳过网络请求")

        # 策略3: 导入搜索结果 JSON
        if from_search_file:
            try:
                external = load_search_results_json(from_search_file)
                external_for_brand = [
                    e for e in external
                    if e.get("brand") == brand and e["model"] not in existing_brand
                ]
                existing_found = {d["model"] for d in brand_discovered}
                new_ext = [e for e in external_for_brand if e["model"] not in existing_found]
                brand_discovered.extend(new_ext)
                if new_ext:
                    report.append(f"  - 外部导入: {len(new_ext)} 个新型号")
            except Exception as e:
                report.append(f"  - 外部导入: 失败 ({e})")

        # 为每个发现推断面系列
        for d in brand_discovered:
            if not d.get("series"):
                d.update(infer_specs(brand, d["model"], config))

        if brand_discovered:
            report.append(f"  - 合计发现: {len(brand_discovered)} 个")
            for d in brand_discovered[:10]:
                report.append(
                    f"    [{d.get('method','?')}] {d['model']} "
                    f"(series={d.get('series','?')})"
                )
        else:
            report.append(f"  - 无新型号")

        all_discovered.extend(brand_discovered)

    # 去重
    fresh, dupes = deduplicate(all_discovered, competitor_db)

    report.append(f"\n## 汇总\n- 发现: {len(all_discovered)} | 新增: {len(fresh)} | 重复: {len(dupes)}")

    # 对标
    matched, pending = [], []
    for entry in fresh:
        if entry.get("xRange") and entry.get("zRepeat"):
            result = match_competitor(
                product_db, entry["brand"],
                entry.get("series", ""),
                entry["xRange"], entry["zRepeat"],
            )
            entry["hikModel"] = result["hikModel"]
            entry["hikSeries"] = result["hikSeries"]
            entry["_confidence"] = result["confidence"]
            entry["_warnings"] = result.get("warnings", [])
            entry["_hik_xFar"] = result.get("xFar")
            entry["_hik_zRepeat"] = result.get("zRepeat")
            matched.append(entry)
        else:
            entry["_confidence"] = "pending_specs"
            entry["_note"] = "仅有型号名, 需补充 xRange/zRepeat"
            pending.append(entry)

    report.append(f"- 已对标: {len(matched)} | 待补充规格: {len(pending)}")

    # 详情
    if matched:
        report.append(f"\n## 自动对标结果")
        for e in matched:
            conf = e.get("_confidence", "?")
            mark = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}.get(conf, "[?]")
            report.append(
                f"  {mark} {e['brand']} {e['model']} -> {e['hikModel']} "
                f"(series={e['hikSeries']}, xFar={e.get('_hik_xFar')}mm)"
            )
            for w in e.get("_warnings", []):
                report.append(f"    ⚠ {w}")

    if pending:
        report.append(f"\n## 待补充规格 ({len(pending)}条)")
        for e in pending:
            report.append(f"  - {e['brand']} {e['model']} [{e.get('method','?')}]")

    # 生成 JS
    if matched or pending:
        js_block = f"// === 自动发现: {now} ===\n"
        if matched:
            js_block += f"// 已自动对标 {len(matched)} 条\n"
            for e in matched:
                clean = {k: v for k, v in e.items()
                        if not k.startswith("_") and k not in ("method", "source")}
                js_block += gen_js_entry(clean) + "\n"
        if pending:
            js_block += f"// 待补充规格 ({len(pending)}条)\n"
            for e in pending:
                js_block += f"// TODO: {e['brand']} {e['model']} (series={e.get('series','?')}, src={e.get('method','?')})\n"
        js_block += "// === 结束 ===\n"

        report.append(f"\n## 生成代码\n```javascript\n{js_block}\n```")

        if not dry_run and matched:
            clean_entries = [
                {k: v for k, v in e.items()
                 if not k.startswith("_") and k not in ("method", "source")}
                for e in matched
            ]
            from auto_update import update_index_html
            update_index_html(index_path, clean_entries, backup=True)

            if push:
                try:
                    subprocess.run(["git", "add", index_path], check=True)
                    subprocess.run(["git", "commit", "-m",
                        f"Auto-update: {len(matched)} new competitor models ({now[:10]})"],
                        check=False)
                    subprocess.run(["git", "push"], check=False)
                    report.append("\n已推送到 Git 仓库")
                except Exception as e:
                    report.append(f"\nGit 推送失败: {e}")

    report_text = "\n".join(report)
    return report_text, matched, pending


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="海康3D轮廓仪 — 全自动竞品监控 v2")
    parser.add_argument("--brand", help="仅监控指定品牌")
    parser.add_argument("--index", default="index.html")
    parser.add_argument("--apply", action="store_true", help="实际更新 index.html")
    parser.add_argument("--push", action="store_true", help="更新后 git push")
    parser.add_argument("--skip-network", action="store_true",
                       help="跳过网络请求 (仅本地分析)")
    parser.add_argument("--from-search", help="从 Claude WebSearch 结果的 JSON 文件导入")
    parser.add_argument("--output-report", help="保存报告到文件")
    args = parser.parse_args()

    brands = [args.brand] if args.brand else None
    dry_run = not args.apply

    header = f"""
{'='*60}
  海康3D轮廓仪 — 竞品自动监控 v2
  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
  模式: {'预览' if dry_run else '正式更新'}
  网络: {'跳过' if args.skip_network else '启用 (直接抓取 + 搜索引擎)'}
  品牌: {', '.join(brands) if brands else '全部 (9个)'}
  外部数据: {args.from_search or '无'}
{'='*60}
"""
    print(header)

    report, matched, pending = run_monitor_cycle(
        index_path=args.index,
        brands=brands,
        dry_run=dry_run,
        push=args.push and not dry_run,
        skip_network=args.skip_network,
        from_search_file=args.from_search,
    )

    print(report)

    if args.output_report:
        with open(args.output_report, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n[报告] {args.output_report}")

    if matched and dry_run:
        print(f"\n发现 {len(matched)} 个新型号可对标. 使用 --apply 实际更新.")


if __name__ == "__main__":
    main()
