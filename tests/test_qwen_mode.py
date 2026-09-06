"""qwen 实时模式单元测试（mock 传输层，无需真实 API Key）"""
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import generator


def fake_dashscope(content: str, capture: dict | None = None):
    """构造 httpx.post 替身，返回固定 content"""

    def _post(url, headers=None, json=None, timeout=None):
        if capture is not None:
            capture.update(url=url, headers=headers, payload=json)
        class _R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": content}}]}
        return _R()

    return _post


def test_extract_json_tolerates_markdown_fence():
    text = '好的，结果如下：```json\n{"title": "X", "bullets": ["a"]}\n```\n以上。'
    assert generator._extract_json(text) == {"title": "X", "bullets": ["a"]}


def test_dashscope_chat_builds_vl_message(monkeypatch):
    capture: dict = {}
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(httpx, "post", fake_dashscope('{"ok": 1}', capture))
    out = generator._dashscope_chat([{"role": "user", "content": "识别商品"}],
                                    model=generator.VL_MODEL, image_b64="AAAA")
    assert out == '{"ok": 1}'
    msg = capture["payload"]["messages"][0]
    assert msg["content"][0]["type"] == "image_url"
    assert msg["content"][0]["image_url"]["url"].startswith("data:image/png;base64,AAAA")
    assert capture["headers"]["Authorization"] == "Bearer sk-test"
    assert capture["payload"]["model"] == generator.VL_MODEL


def test_structure_real_path_parses_pim(monkeypatch):
    real = {"product_name": "智能保温杯", "category": "保温杯", "category_en": "Insulated Water Bottle",
            "attributes": {"material": "Stainless Steel"}, "selling_points": ["Keeps cold 24h"],
            "keywords": ["thermos"], "target_audience": "commuters", "use_scenarios": ["office"]}
    monkeypatch.setattr(generator, "MODE", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(httpx, "post", fake_dashscope(json.dumps(real, ensure_ascii=False)))
    pim = generator.structure_product("智能保温杯", "保温杯", ["保温24小时"], 9.9, "")
    assert pim["category_en"] == "Insulated Water Bottle"
    assert pim["source"] == "百炼 " + generator.CHAT_MODEL  # 无图入参走文本模型


def test_generate_real_path_parses_listing(monkeypatch):
    real = {"title": "Great Bottle", "bullets": ["A", "B", "C", "D", "E"],
            "description": "desc", "seo_meta": "meta"}
    monkeypatch.setattr(generator, "MODE", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(httpx, "post", fake_dashscope(json.dumps(real, ensure_ascii=False)))
    data = generator.generate_listing(generator.structure_product_mock(
        "保温杯", "保温杯", ["保温"], 9.9, ""), "amazon", "en")
    assert data["title"] == "Great Bottle"
    assert data["source"] == "百炼 " + generator.CHAT_MODEL


def test_structure_degrades_to_mock_on_error(monkeypatch):
    """百炼调用失败 → 自动降级 mock 且 source 标注原因（Demo 永不中断承诺）"""
    monkeypatch.setattr(generator, "MODE", "qwen")

    def boom(*args, **kwargs):
        raise RuntimeError("网络超时")

    monkeypatch.setattr(generator, "structure_product_real", boom)
    pim = generator.structure_product("智能保温杯", "保温杯", ["保温24小时"], 9.9, "")
    assert pim["source"].startswith("mock（百炼调用失败: RuntimeError）")
    assert pim["attributes"]["category"] == "Insulated Water Bottle"  # mock 数据完整


def test_generate_degrades_to_mock_on_error(monkeypatch):
    monkeypatch.setattr(generator, "MODE", "qwen")

    def boom(*args, **kwargs):
        raise RuntimeError("限流")

    monkeypatch.setattr(generator, "generate_listing_real", boom)
    pim = generator.structure_product_mock("保温杯", "保温杯", ["保温"], 9.9, "")
    data = generator.generate_listing(pim, "amazon", "en")
    assert data["source"] == "mock" and data["title"]
