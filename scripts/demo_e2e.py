# -*- coding: utf-8 -*-
"""ListingForge 一键 E2E 演示脚本：生成 → 校验 → 改写 → 放行 → 上架

用法: 先启动服务(python run.py)，另开终端执行
      python scripts/demo_e2e.py [sample_key]
"""
import json
import sys

import httpx

B = "http://127.0.0.1:8000"


def banner(t):
    print(f"\n{'=' * 8} {t} {'=' * 8}")


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "bottle"
    c = httpx.Client(timeout=60)
    meta = c.get(f"{B}/api/meta").json()
    banner(f"ListingForge E2E · 模式: {meta['mode']}")

    banner("1. 商品录入")
    p = c.post(f"{B}/api/products/sample/{key}").json()
    pid = p["id"]
    print(f"   商品 #{pid} {p['name']} · 类目 {p['category']} · ${p['price']}")

    banner("2. AI 结构化 (F1) + 图片管线 (F3)")
    r = c.post(f"{B}/api/products/{pid}/structure").json()
    pim = r["product"]["pim"]
    print(f"   来源: {pim['source']}")
    print(f"   属性: {json.dumps(pim['attributes'], ensure_ascii=False)}")
    print(f"   卖点: {len(pim['selling_points'])} 条 · 关键词: {', '.join(pim['keywords'][:5])}")
    print(f"   主图: {r['images']['main']}")

    banner("3. 多平台文案生成 (F2): 4 平台 × EN/ES")
    data = {"platforms": ["amazon", "aliexpress", "tiktok_shop", "shopify"],
            "languages": ["en", "es"]}
    ls = c.post(f"{B}/api/products/{pid}/generate", data=data).json()["listings"]
    for l in ls[:2]:
        print(f"   [{l['platform']}/{l['language']}] {l['title'][:70]}")
    print(f"   … 共 {len(ls)} 条")

    banner("4. 规则引擎校验 (F4)")
    alx = next(l for l in ls if l["platform"] == "aliexpress" and l["language"] == "en")
    rep = c.get(f"{B}/api/listings/{alx['id']}/validate").json()
    print(f"   速卖通(改写前): {rep['summary']}")
    rf = c.post(f"{B}/api/listings/{alx['id']}/autofix").json()
    print(f"   自动改写: {[f['rule'] for f in rf['fix_log']['fixed']]} → {rf['report']['summary']}")

    banner("5. 审核放行 (F5)")
    approved = 0
    for l in ls:
        if l["language"] == "en":
            c.post(f"{B}/api/listings/{l['id']}/approve")
            approved += 1
    print(f"   已放行 {approved} 条 EN 主语言 Listing")

    banner("6. 多平台一键上架 (F6)")
    r = c.post(f"{B}/api/products/{pid}/publish").json()
    for t in r["tasks"]:
        print(f"   {t['platform']:<12} {t['status']}  {t['message']}")

    print("\n✅ E2E 演示完成，浏览器打开 http://127.0.0.1:8000 可查看该商品全流程数据")


if __name__ == "__main__":
    main()
