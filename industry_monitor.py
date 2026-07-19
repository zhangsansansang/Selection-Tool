#!/usr/bin/env python3
"""
行业新闻聚合监控 — 稳定可靠的竞品发现渠道
=============================================
设计理念: 不直接爬友商网站(被拦截风险高), 改为监控行业新闻聚合站.
这些站点天然汇总所有品牌的新品发布, 格式稳定, 不易被拦截.

数据源:
  - 机器视觉网 (china-vision.org) — 国内最大机器视觉行业媒体
  - 中国工控网 (gongkong.com) — 工业自动化新品发布
  - DuckDuckGo 搜索 — 通用备选方案

用法:
  python industry_monitor.py                     # 全品牌监控
  python industry_monitor.py --apply --push       # 更新并推送
"""

import re
import json
import sys
import os
import hashlib
import argparse
import subprocess
from datetime import datetime
from collections import defaultdict
from urllib.parse import quote_plus

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from auto_update import (
    load_product_db, load_competitor_db, match_competitor,
    deduplicate, gen_js_entry, SERIES_MAP,
)

# ============================================================
# 行业新闻聚合源（稳定的 RSS / 新闻列表页）
# ============================================================

NEWS_SOURCES = [
    {
        "name": "机器视觉网-新品",
        "url": "https://www.china-vision.org/news/",
        "type": "html",
        "selector": ".news-title, .news_title, h3 a, .title a",
    },
    {
        "name": "中国工控网-新品发布",
        "url": "https://www.gongkong.com/news/",
        "type": "html",
        "selector": ".newsTitle a, .title a, h2 a",
    },
    {
        "name": "传感器专家网-新品",
        "url": "https://www.sensorexpert.com.cn/article/",
        "type": "html",
        "selector": ".title a, h3 a, .news-title",
    },
]

# ============================================================
# 品牌关键词 → 触发提取型号
# ============================================================

BRAND_KEYWORDS = {
    "Keyence": ["keyence", "基恩士", "LJ-X", "LJ-V", "LJ-S"],
    "LMI": ["LMI", "gocator", "Gocator", "G2", "G3", "G4", "G6"],
    "SSZN": ["深视智能", "SSZN", "SRI", "SR系列"],
    "Photon": ["光子", "photon", "phoskey", "GL-8", "GL-9"],
    "Sick": ["sick", "西克", "ruler", "Ruler"],
    "Huaray": ["华睿", "huaray", "DL3", "DL5"],
    "翌视": ["翌视", "nextvision", "LVM"],
    "Elsen": ["埃尔森", "elsen", "AT-S"],
    "Meca": ["梅卡", "meca", "LNX"],
    "OPT": ["奥普特", "opt ", "OPT-", "LPE", "LPF", "LPH", "LPD", "FPB", "FPC", "LSA"],
}

# 全品牌型号正则
ALL_MODEL_PATTERN = re.compile(
    r"(?:LJ-[VSX]\d{4})|"                      # Keyence
    r"(?:G\d{4})|"                               # LMI
    r"(?:SR[IA]?\d{4,5}[A-Za-z]?)|"             # SSZN
    r"(?:GL-\d{4,5}D?)|"                        # Photon
    r"(?:Ruler\d{4})|"                           # Sick
    r"(?:DL\d{4}[A-Za-z]?(?:-[A-Za-z0-9]+)?)|"  # Huaray
    r"(?:LVM\d{4}[A-Za-z]*)|"                    # 翌视
    r"(?:AT-S\d{4}-\d{2}[A-Za-z]-S?\d+)|"       # Elsen
    r"(?:LNX-\d{4,5})|"                          # Meca
    r"(?:OPT-[A-Z]{2,4}\d?-\d{2,4}(?:-\d{2})?)", # OPT
    re.IGNORECASE
)


# ============================================================
# 核心: 从行业新闻中提取型号
# ============================================================

def fetch_news_page(url, timeout=10):
    """抓取新闻列表页 HTML"""
    try:
        import urllib.request
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def extract_models_from_news(html):
    """从新闻 HTML 中提取所有品牌的型号"""
    if not html:
        return []
    return list(set(ALL_MODEL_PATTERN.findall(html)))


def search_news_for_brand(brand, timeout=10):
    """用 DuckDuckGo 搜索某品牌的最新新闻"""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    keywords = BRAND_KEYWORDS.get(brand, [brand])
    models_found = set()

    for kw in keywords[:2]:
        try:
            query = f"{kw} 新型号 发布 2025 2026 3D 线激光 轮廓仪"
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            text = " ".join(s.get_text() for s in soup.select(".result__snippet"))

            # 从搜索结果摘要中提取型号
            found = set(ALL_MODEL_PATTERN.findall(text))
            models_found.update(found)
        except Exception:
            continue

    return list(models_found)


# ============================================================
# 主监控流程
# ============================================================

def get_existing_models(competitor_db):
    """返回 {(brand, model)} 集合"""
    return {(c["brand"], c["model"]) for c in competitor_db}


def match_brand_from_model(model_str):
    """根据型号字符串判断属于哪个品牌"""
    model_upper = model_str.upper()
    if model_upper.startswith("LJ-"):
        return "Keyence"
    if model_upper.startswith("G") and model_upper[1:].isdigit():
        return "LMI"
    if model_upper.startswith("SR") or model_upper.startswith("SRI"):
        return "SSZN"
    if model_upper.startswith("GL-"):
        return "Photon"
    if model_upper.startswith("RULER"):
        return "Sick"
    if model_upper.startswith("DL"):
        return "Huaray"
    if model_upper.startswith("LVM"):
        return "翌视"
    if model_upper.startswith("AT-S"):
        return "Elsen"
    if model_upper.startswith("LNX-"):
        return "Meca"
    if model_upper.startswith("OPT-"):
        return "OPT"
    return None


def run_industry_monitor(index_path="index.html", dry_run=True, push=False):
    """运行行业新闻监控"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = [f"# 行业新闻监控报告\n时间: {now}\n"]

    product_db = load_product_db(index_path)
    competitor_db = load_competitor_db(index_path)
    existing = get_existing_models(competitor_db)

    report.append(f"## 基线\n海康: {len(product_db)} 款 | 竞品: {len(competitor_db)} 条\n")

    all_discovered = []

    # === 策略1: 行业新闻聚合站 ===
    report.append("## 策略1: 行业新闻聚合站\n")
    for src in NEWS_SOURCES:
        html = fetch_news_page(src["url"])
        if html:
            models = extract_models_from_news(html)
            report.append(f"- {src['name']}: 发现 {len(models)} 个型号")
            for m in models:
                brand = match_brand_from_model(m)
                if brand and (brand, m) not in existing:
                    all_discovered.append({
                        "brand": brand, "model": m,
                        "source": src["name"], "method": "industry_news",
                    })
        else:
            report.append(f"- {src['name']}: 无法访问 (可能需要 GitHub Actions 云环境)")

    # === 策略2: DuckDuckGo 搜索 (每品牌) ===
    report.append("\n## 策略2: 搜索引擎\n")
    for brand in BRAND_KEYWORDS:
        existing_brand_models = {m for b, m in existing if b == brand}
        found = search_news_for_brand(brand)
        new_for_brand = [m for m in found if m not in existing_brand_models]
        if new_for_brand:
            report.append(f"- {brand}: 发现 {len(new_for_brand)} 个潜在新型号")
            for m in new_for_brand:
                if (brand, m) not in {(d["brand"], d["model"]) for d in all_discovered}:
                    all_discovered.append({
                        "brand": brand, "model": m,
                        "source": "search", "method": "search_engine",
                    })

    # 去重
    fresh, dupes = deduplicate(all_discovered, competitor_db)
    report.append(f"\n## 汇总\n发现: {len(all_discovered)} | 新增: {len(fresh)} | 重复: {len(dupes)}")

    # 推断面系列并对标
    matched, pending = [], []
    for entry in fresh:
        # 推断系列
        if not entry.get("series"):
            from auto_update import lookup_series
            for known_series in SERIES_MAP.get(entry["brand"], {}):
                if known_series.lower() in entry["model"].lower():
                    entry["series"] = known_series
                    break

        # 对标 (仅有型号名时仍可尝试, 系列已推断)
        result = match_competitor(
            product_db, entry["brand"],
            entry.get("series", ""),
            entry.get("xRange", 0) if entry.get("xRange") else 50,
            entry.get("zRepeat", 0) if entry.get("zRepeat") else 1,
        )

        if result["hikModel"] or result["hikSeries"] == "NotLineLaser":
            entry["hikModel"] = result["hikModel"]
            entry["hikSeries"] = result["hikSeries"]
            entry["_confidence"] = result["confidence"]
            entry["_warnings"] = result.get("warnings", [])
            matched.append(entry)
        else:
            entry["_confidence"] = "pending_specs"
            pending.append(entry)

    report.append(f"已对标: {len(matched)} | 待补充: {len(pending)}")

    # 生成代码并更新
    if matched and not dry_run:
        clean = [{k: v for k, v in e.items() if not k.startswith("_")} for e in matched]
        from auto_update import update_index_html
        update_index_html(index_path, clean, backup=True)

        if push:
            try:
                subprocess.run(["git", "add", index_path], check=True)
                subprocess.run(["git", "commit", "-m",
                    f"Auto-monitor: {len(matched)} new models from industry news ({now[:10]})"],
                    check=False)
                subprocess.run(["git", "push"], check=False)
                report.append("\n已推送到 Git")
            except Exception as e:
                report.append(f"\nGit推送失败: {e}")

    report_text = "\n".join(report)
    return report_text, matched, pending


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="行业新闻聚合监控")
    parser.add_argument("--index", default="index.html")
    parser.add_argument("--apply", action="store_true", help="实际更新")
    parser.add_argument("--push", action="store_true", help="更新后推送")
    parser.add_argument("--output-report", help="保存报告")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  行业新闻聚合监控")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  数据源: {len(NEWS_SOURCES)} 个行业媒体 + DuckDuckGo")
    print(f"{'='*60}\n")

    report, matched, pending = run_industry_monitor(
        index_path=args.index,
        dry_run=not args.apply,
        push=args.push and args.apply,
    )
    print(report)

    if args.output_report:
        with open(args.output_report, "w", encoding="utf-8") as f:
            f.write(report)


if __name__ == "__main__":
    main()
