"""文案引擎单元测试：结构化 / 标题约束 / 本地化 / 中英混排防护"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.generator import (LOCALIZED_LIBRARY, PLATFORM_SPEC, _short,
                           generate_listing_mock, structure_product_mock)

PIM_BOTTLE = structure_product_mock("智能温显保温杯 500ml", "保温杯",
                                    ["LED温度显示", "304不锈钢真空内胆保温24小时"],
                                    25.99, "欧美通勤族与健身人群")


def test_short_semantic_truncation():
    assert _short("Vacuum-insulated: keeps drinks cold 24h / hot 12h", 26) == "Vacuum-insulated"
    assert _short("no comma phrase that is quite long indeed", 20) == "no comma phrase"
    assert _short("short", 10) == "short"


def test_structure_detects_material_not_bluetooth_color():
    assert PIM_BOTTLE["attributes"]["material"] == "Stainless Steel"
    assert PIM_BOTTLE["attributes"]["capacity"] == "500ml"
    pim_earbuds = structure_product_mock("无线蓝牙降噪耳机 Pro", "耳机", ["蓝牙5.3稳定连接"], 49.99, "")
    assert pim_earbuds["attributes"]["color"] != "Ocean Blue"  # 「蓝牙」不再误判为蓝色


def test_titles_within_platform_limits():
    for platform, spec in PLATFORM_SPEC.items():
        title = generate_listing_mock(PIM_BOTTLE, platform, "en")
        if platform != "aliexpress":  # 速卖通 mock 稿故意含促销词，交规则引擎改写
            assert len(title["title"]) <= spec["title_max"], (platform, title["title"])


def test_no_cjk_in_english_copy():
    for platform in PLATFORM_SPEC:
        l = generate_listing_mock(PIM_BOTTLE, platform, "en")
        text = l["title"] + " ".join(l["bullets"]) + l["description"] + l.get("seo_meta", "")
        assert not re.search(r"[\u4e00-\u9fff]", text), text


def test_localized_rewrite_hits_library():
    es = generate_listing_mock(PIM_BOTTLE, "amazon", "es")
    assert es["title"].startswith("Botella Térmica")
    assert es["bullets"] and es["description"]
    ar = generate_listing_mock(PIM_BOTTLE, "tiktok_shop", "ar")
    assert re.search(r"[\u0600-\u06FF]", ar["title"])  # 阿语字符
    pt = generate_listing_mock(PIM_BOTTLE, "shopify", "pt")
    assert "Garrafa" in pt["title"] or "Aurora" in pt["title"]


def test_localized_fallback_for_unknown_category():
    """未命中类目文案库 → 词库映射 + 本地化框架改写（v1.3 T5 盲区补齐）"""
    pim = structure_product_mock("竹制软毛牙刷 4 支装", "牙刷", ["软毛呵护牙龈"], 6.99, "")
    assert pim["category_en"] not in LOCALIZED_LIBRARY  # 走 fallback 分支
    es = generate_listing_mock(pim, "amazon", "es")
    assert es["description"].startswith("¡Descubre")  # 本地化开场
    assert es["description"].endswith("¡Cómpralo ahora!")  # 本地化收尾
    assert es["title"] and es["bullets"]


def test_titles_layout_core_keywords():
    """标题关键词布局 ≥2 命中（v1.2 R9 对应生成端保证）"""
    kws = PIM_BOTTLE.get("keywords", [])
    for platform in PLATFORM_SPEC:
        title = generate_listing_mock(PIM_BOTTLE, platform, "en")["title"]
        hits = sum(1 for k in kws if k.lower() in title.lower())
        assert hits >= 2, (platform, title, kws)


def test_aliexpress_mock_contains_promo_words_for_demo():
    t = generate_listing_mock(PIM_BOTTLE, "aliexpress", "en")["title"]
    assert "Hot Sale" in t or "Free Shipping" in t  # 规则引擎演示剧本的一部分
