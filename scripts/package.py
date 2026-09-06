# -*- coding: utf-8 -*-
"""一键打包交付 zip：git archive + 追加 CI 工作流 + 完整性自检

用法: python scripts/package.py
产物: ../AI跨境黑客松_完整交付_ListingForge.zip
"""
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP_PATH = ROOT.parent / "AI跨境黑客松_完整交付_ListingForge.zip"
CI_FILE = ".github/workflows/ci.yml"

REQUIRED = [
    "ListingForge/README.md",
    "ListingForge/run.py",
    "ListingForge/requirements.txt",
    "ListingForge/CHANGELOG.md",
    "ListingForge/LICENSE",
    "ListingForge/app/main.py",
    "ListingForge/app/rules_engine.py",
    "ListingForge/app/generator.py",
    "ListingForge/app/imaging.py",
    "ListingForge/app/rules/amazon.json",
    "ListingForge/app/rules/aliexpress.json",
    "ListingForge/app/rules/tiktok_shop.json",
    "ListingForge/app/rules/shopify.json",
    "ListingForge/app/static/index.html",
    "ListingForge/app/static/app.js",
    "ListingForge/tests/test_api.py",
    "ListingForge/scripts/demo_e2e.py",
    "ListingForge/scripts/ui_smoke.py",
    "ListingForge/docs/技术说明.md",
    "ListingForge/docs/体验方式.md",
    "ListingForge/video/listingforge_demo.mp4",
    "ListingForge/.github/workflows/ci.yml",
]


def main():
    # 1. 干净工作树检查
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                           cwd=ROOT).stdout.strip()
    if dirty:
        print(f"⚠ 工作树有未提交变更（将按 HEAD 打包）：\n{dirty}")
    # 2. git archive
    subprocess.run(["git", "archive", f"--prefix=ListingForge/", "-o", str(ZIP_PATH), "HEAD"],
                   cwd=ROOT, check=True)
    # 3. 追加未入库的 CI 工作流（推送受 token workflow scope 限制）
    with zipfile.ZipFile(ZIP_PATH, "a") as z:
        z.write(ROOT / CI_FILE, f"ListingForge/{CI_FILE}")
    # 4. 完整性自检
    names = set(zipfile.ZipFile(ZIP_PATH).namelist())
    missing = [f for f in REQUIRED if f not in names]
    size_mb = ZIP_PATH.stat().st_size / 1048576
    print(f"打包完成: {ZIP_PATH.name}")
    print(f"  文件数 {len(names)} | 大小 {size_mb:.1f} MB")
    if missing:
        print("  ✗ 缺失关键文件:")
        for f in missing:
            print("   -", f)
        sys.exit(1)
    print(f"  ✓ 自检通过（{len(REQUIRED)} 个关键文件齐全）")


if __name__ == "__main__":
    main()
