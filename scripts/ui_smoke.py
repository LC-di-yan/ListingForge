# -*- coding: utf-8 -*-
"""ListingForge UI 冒烟测试（Playwright 真浏览器走六步流并断言）

依赖: pip install playwright httpx && playwright install chromium
用法: 服务运行中(python run.py)时执行  python scripts/ui_smoke.py
输出: 每步 ✓/✗ + 最终 PASS/FAIL（进程退出码 0/1）
"""
import sys

from playwright.sync_api import sync_playwright

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'✓' if ok else '✗'} {name}" + (f"（{detail}）" if detail and not ok else ""))


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        page.wait_for_selector(".sample-card")
        page.wait_for_timeout(800)

        print("1) 商品录入")
        page.click('#steps li[data-step="1"]')
        page.wait_for_selector("#panel-1.active")
        page.click(".sample-card:nth-child(1)")
        page.wait_for_selector("#panel-2.active")
        pid = page.evaluate("state.product.id")
        check("示例创建并进入第 2 步", pid is not None)

        print("2) AI 结构化")
        page.click("#btnStructure")
        page.wait_for_selector("#structureResult:not(.hidden)", timeout=30000)
        page.wait_for_timeout(1500)
        kv = page.locator("#pimAttrs .kv").count()
        imgs_ok = page.evaluate("document.getElementById('imgMain').naturalWidth > 0")
        check("PIM 属性渲染", kv >= 5, f"kv={kv}")
        check("白底主图加载", imgs_ok)

        print("3) 文案生成")
        page.click("#goto3")
        page.wait_for_selector("#panel-3.active")
        page.click("#pickLanguages .chip:nth-child(2)")  # 勾选西语
        page.click("#btnGenerate")
        page.wait_for_selector("#generateResult:not(.hidden)", timeout=60000)
        page.wait_for_timeout(1200)
        n = page.evaluate("state.listings.length")
        check("生成 8 条物料", n == 8, f"n={n}")
        page.click("#btnExpandAll")
        page.wait_for_timeout(300)
        cards = page.locator("#genPreview .listing-card").count()
        check("展开全部物料", cards == 8, f"cards={cards}")

        print("4) 规则校验")
        page.click("#goto4")
        page.wait_for_selector("#panel-4.active")
        page.click("#btnValidateAll")
        page.wait_for_timeout(900)
        rows = page.locator(".matrix-row").count()
        check("校验矩阵 8+1 行", rows == 9, f"rows={rows}")
        page.click("#btnAutofix")
        page.wait_for_timeout(800)
        rep_ok = page.locator("#reportArea .report-summary").count() > 0
        check("违规改写后报告渲染", rep_ok)

        print("5) 审核放行")
        page.click("#goto5")
        page.wait_for_selector("#panel-5.active")
        page.wait_for_timeout(600)
        page.fill("#reviewArea .ed-title", page.input_value("#reviewArea .ed-title") + " (QC)")
        page.click("#btnSaveDraft")
        page.wait_for_timeout(500)
        saved = page.evaluate("state.listings.some(l => l.title.includes('(QC)'))")
        check("保存草稿生效", saved)
        page.click("#btnApproveAll")
        page.wait_for_timeout(800)
        approved = page.evaluate("state.listings.filter(l => l.status === 'approved').length")
        check("批量放行 EN", approved == 4, f"approved={approved}")

        print("6) 一键上架")
        page.click("#goto6")
        page.wait_for_selector("#panel-6.active")
        page.click("#btnPublish")
        page.wait_for_selector("#publishResult:not(.hidden)", timeout=30000)
        page.wait_for_timeout(600)
        ok = page.evaluate("state.tasks.every(t => t.status === 'success')")
        check("四平台上架成功", ok and page.evaluate("state.tasks.length") == 4)

        check("无页面 JS 错误", not errors, "; ".join(errors[:2]))
        browser.close()

    passed = all(CHECKS)
    print(f"\n{'✅ UI 冒烟 PASS' if passed else '❌ UI 冒烟 FAIL'}（{sum(CHECKS)}/{len(CHECKS)} 项）")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
