"""规则引擎单元测试：校验 + 自动改写"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import imaging, rules_engine

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def base_listing():
    return {
        "title": "Insulated Water Bottle Stainless Steel Classic Black with Smart LED temperature display for travel",
        "bullets": ["A" * 100, "B" * 100, "C" * 100, "D" * 100, "E" * 100],
        "description": "x" * 300,
        "seo_meta": "m" * 140,
    }


def test_clean_amazon_listing_passes(tmp_path):
    main = imaging.make_white_bg(ASSETS / "sample_bottle.png", tmp_path / "main.jpg")
    report = rules_engine.validate("amazon", base_listing(), main, {"attributes": {}, "keywords": []})
    assert report["passed"], [c for c in report["checks"] if c["status"] == "fail"]
    assert len(report["checks"]) == 10  # v1.2: 新增 title_keywords 规则


def test_keyword_hits_rule():
    pim = {"keywords": ["insulated water bottle", "thermos", "travel mug"]}
    l = base_listing()
    l["title"] = "Insulated Water Bottle Stainless Steel thermos for travel"
    check = next(c for c in rules_engine.validate("amazon", l, "", pim)["checks"]
                 if c["id"] == "title_keywords")
    assert check["status"] == "pass" and "命中 2/3" in check["observed"]
    l["title"] = "Completely unrelated product title text"
    check = next(c for c in rules_engine.validate("amazon", l, "", pim)["checks"]
                 if c["id"] == "title_keywords")
    assert check["status"] == "warn"  # warn 级：不影响 passed，但提示布局


def test_word_boundary_truncation_everywhere():
    l = base_listing()
    l["title"] = "word " * 80
    fixed, _ = rules_engine.autofix("amazon", l, "", None)
    assert len(fixed["title"]) <= 200 and not fixed["title"].endswith("wor")
    l2 = base_listing()
    l2["bullets"] = ["alpha " * 80]  # 400 字符，规则上限 240
    fixed2, log2 = rules_engine.autofix("amazon", l2, "", None)
    assert len(fixed2["bullets"][0]) <= 240
    assert not fixed2["bullets"][0].endswith("alp")
    assert any(f["rule"] == "bullets_length" for f in log2["fixed"])


def test_banned_word_detected_and_autofixed():
    l = base_listing()
    l["title"] = "Hot Sale Best Insulated Water Bottle #1 Free Shipping"
    report = rules_engine.validate("amazon", l, "", None)
    banned = next(c for c in report["checks"] if c["id"] == "title_banned")
    assert banned["status"] == "fail" and "Hot Sale" in banned["observed"]
    fixed, fix_log = rules_engine.autofix("amazon", l, "", None)
    assert any(f["rule"] == "title_banned" for f in fix_log["fixed"])
    assert "hot sale" not in fixed["title"].lower() and "#1" not in fixed["title"]
    assert rules_engine.validate("amazon", fixed, "", None)["checks"][1]["status"] == "pass"


def test_title_truncation_at_word_boundary():
    l = base_listing()
    l["title"] = "word " * 80  # 400 字符
    fixed, fix_log = rules_engine.autofix("amazon", l, "", None)
    assert len(fixed["title"]) <= 200
    assert not fixed["title"].endswith("wor")  # 不留半个词
    assert any(f["rule"] == "title_length" for f in fix_log["fixed"])


def test_bullets_count_autofix():
    l = base_listing()
    l["bullets"] = ["only one"]
    fixed, fix_log = rules_engine.autofix("amazon", l, "", None)
    assert len(fixed["bullets"]) == 5
    assert any(f["rule"] == "bullets_count" for f in fix_log["fixed"])


def test_aliexpress_attr_required():
    l = base_listing()
    report = rules_engine.validate("aliexpress", l, "", None)
    attr = next(c for c in report["checks"] if c["id"] == "attr_required")
    assert attr["status"] == "fail"
    fixed, _ = rules_engine.autofix("aliexpress", l, "", {"attributes": {"material": "Steel"}})
    assert fixed is not None  # autofill_attr 直接改 pim（返回后由调用方持久化）


def test_image_rules_measure_real_pixels(tmp_path):
    main = imaging.make_white_bg(ASSETS / "sample_bottle.png", tmp_path / "main.jpg")
    report = rules_engine.validate("amazon", base_listing(), main, None)
    for cid in ("image_ratio", "image_white_bg", "image_min_px"):
        check = next(c for c in report["checks"] if c["id"] == cid)
        assert check["status"] == "pass", check


def test_rules_hot_reload(tmp_path):
    """修改规则 JSON 后无需重启即生效"""
    import json
    import shutil
    rules_dir = Path(rules_engine.RULES_DIR)
    backup = rules_dir / "shopify.backup.json"
    shutil.copy(rules_dir / "shopify.json", backup)
    try:
        data = json.loads((rules_dir / "shopify.json").read_text(encoding="utf-8"))
        data["rules"].append({"id": "dummy_rule", "field": "title", "type": "length_max",
                              "max": 10, "severity": "error", "name": "临时规则"})
        (rules_dir / "shopify.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        report = rules_engine.validate("shopify", base_listing(), "", None)
        assert any(c["id"] == "dummy_rule" for c in report["checks"])
    finally:
        shutil.move(backup, rules_dir / "shopify.json")
        rules_engine._RULE_CACHE.pop("shopify", None)
