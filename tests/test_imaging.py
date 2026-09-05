"""图片管线测试：白底规范 / 幂等缓存 / 多尺寸产物"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import imaging

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def test_white_bg_meets_amazon_spec(tmp_path):
    out = imaging.make_white_bg(ASSETS / "sample_bottle.png", tmp_path / "main.jpg")
    meta = imaging.image_meta(out)
    assert meta["width"] == meta["height"] == 1200
    assert meta["white_ratio"] >= 0.6  # 亚马逊纯白背景规范（规则引擎阈值一致）


def test_process_product_image_outputs_and_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(imaging, "UPLOADS", tmp_path)
    r1 = imaging.process_product_image(ASSETS / "sample_earbuds.png", 42)
    assert r1["cached"] is False
    for key in ("1x1", "4x5", "16x9", "9x16"):
        web = r1["variants"][key]
        assert web.startswith("/data/") and web.endswith(f"variant_{key}.jpg")  # web 路径
        assert (tmp_path / "42" / "images" / f"variant_{key}.jpg").exists()      # 磁盘产物
    r2 = imaging.process_product_image(ASSETS / "sample_earbuds.png", 42)
    assert r2["cached"] is True  # 幂等缓存
    assert r2["main"] == r1["main"]
