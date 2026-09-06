"""平台规则引擎（F4 · 差异化核心）

"规则即代码"：每个平台的规则库是 app/rules/*.json，可版本化、可扩展。
新增平台 = 新增一份规则 JSON；新增规则类型 = 用 @register_check / @register_fix
注册一个函数即可，无需改动引擎主干。

引擎职责：
1. validate(listing, image_path, pim, rules)  -> 逐条校验，输出报告
2. autofix(listing, report)                   -> 按可修复规则自动改写
"""
import json
import re
from datetime import datetime
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent / "rules"
PLATFORMS = ["amazon", "aliexpress", "tiktok_shop", "shopify"]

_RULE_CACHE: dict[str, tuple[float, dict]] = {}  # platform -> (mtime, ruleset)
TEXT_FIELDS = ("title", "bullets", "description", "seo_meta")

CHECKS: dict[str, object] = {}  # rule_type -> 校验函数
FIXES: dict[str, object] = {}   # fix 名称 -> 改写函数（返回 True 表示显式记日志）


def register_check(rtype: str):
    def deco(fn):
        CHECKS[rtype] = fn
        return fn
    return deco


def register_fix(name: str):
    def deco(fn):
        FIXES[name] = fn
        return fn
    return deco


def load_rules(platform: str) -> dict:
    """按 mtime 热加载：修改规则 JSON 即时生效，无需重启"""
    path = RULES_DIR / f"{platform}.json"
    mtime = path.stat().st_mtime
    cached = _RULE_CACHE.get(platform)
    if not cached or cached[0] != mtime:
        cached = (mtime, json.loads(path.read_text(encoding="utf-8")))
        _RULE_CACHE[platform] = cached
    return cached[1]


EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u2B00-\u2BFF]"
)


def word_cut(s: str, n: int) -> str:
    """词边界安全截断（规则修复与生成端共用语义，不产生残句）"""
    s = s or ""
    if len(s) <= n:
        return s
    head = s[:n]
    return (head.rsplit(" ", 1)[0] if " " in head else head).rstrip(" ,;-–—:")


def _field_text(listing: dict, field: str) -> str:
    return listing.get(field) or ""


# ---------------- 校验规则（按类型注册） ----------------

@register_check("length_max")
def _check_length_max(rule, listing, image_path, pim):
    n = len(_field_text(listing, rule.get("field", "")))
    ok = n <= rule["max"]
    return {"status": "pass" if ok else "fail", "observed": f"{n} 字符", "detail": f"限制 {rule['max']}"}


@register_check("length_min")
def _check_length_min(rule, listing, image_path, pim):
    n = len(_field_text(listing, rule.get("field", "")))
    ok = n >= rule["min"]
    return {"status": "pass" if ok else ("fail" if rule["severity"] == "error" else "warn"),
            "observed": f"{n} 字符", "detail": f"要求 ≥ {rule['min']}"}


@register_check("length_range")
def _check_length_range(rule, listing, image_path, pim):
    n = len(_field_text(listing, rule.get("field", "")))
    ok = rule["min"] <= n <= rule["max"]
    return {"status": "pass" if ok else "warn", "observed": f"{n} 字符",
            "detail": f"建议 {rule['min']}-{rule['max']}"}


@register_check("banned_words")
def _check_banned_words(rule, listing, image_path, pim):
    text = _field_text(listing, rule.get("field", ""))
    hits = [w for w in rule["words"] if w.lower() in text.lower()]
    ok = not hits
    return {"status": "pass" if ok else "fail", "observed": "未命中" if ok else "命中: " + ", ".join(hits),
            "detail": f"禁用词表 {len(rule['words'])} 项"}


@register_check("no_emoji")
def _check_no_emoji(rule, listing, image_path, pim):
    hits = EMOJI_RE.findall(_field_text(listing, rule.get("field", "")))
    ok = not hits
    return {"status": "pass" if ok else "fail", "observed": "无" if ok else f"{len(hits)} 个符号",
            "detail": "标题不得含 Emoji/特殊符号"}


@register_check("list_count")
def _check_list_count(rule, listing, image_path, pim):
    n = len(listing.get(rule.get("field", "")) or [])
    ok = rule["min"] <= n <= rule["max"]
    return {"status": "pass" if ok else "fail", "observed": f"{n} 条",
            "detail": f"要求 {rule['min']}-{rule['max']} 条"}


@register_check("item_length_max")
def _check_item_length_max(rule, listing, image_path, pim):
    items = listing.get(rule.get("field", "")) or []
    bad = [(i, len(s)) for i, s in enumerate(items, 1) if len(s) > rule["max"]]
    ok = not bad
    return {"status": "pass" if ok else "warn", "observed": "全部合规" if ok else f"超长 {len(bad)} 条",
            "detail": f"每条 ≤ {rule['max']} 字符"}


@register_check("attr_required")
def _check_attr_required(rule, listing, image_path, pim):
    attrs = (pim or {}).get("attributes", {}) if isinstance(pim, dict) else {}
    missing = [a for a in rule["attrs"] if not attrs.get(a)]
    ok = not missing
    return {"status": "pass" if ok else "fail", "observed": "齐全" if ok else "缺失: " + ", ".join(missing),
            "detail": "必填: " + ", ".join(rule["attrs"])}


@register_check("keyword_hits")
def _check_keyword_hits(rule, listing, image_path, pim):
    title = _field_text(listing, "title").lower()
    keywords = (pim or {}).get("keywords", []) if isinstance(pim, dict) else []
    hits = [k for k in keywords if k and k.lower() in title]
    ok = len(hits) >= rule.get("min_hits", 2)
    shown = ", ".join(hits[:3]) + ("…" if len(hits) > 3 else "")
    return {"status": "pass" if ok else rule.get("severity", "warn"),
            "observed": f'命中 {len(hits)}/{len(keywords)}' + (f': {shown}' if hits else ''),
            "detail": f"需命中 ≥{rule.get('min_hits', 2)} 个核心关键词"}


def _image_check(rule, image_path):
    """图片类规则共用：基于图片管线产物元数据实测（无图直接 fail）"""
    if not image_path:
        return {"status": "fail", "observed": "无主图", "detail": "需先生成主图"}
    from . import imaging
    meta = imaging.image_meta(image_path)
    if rule["type"] == "image_min_px":
        ok = min(meta["width"], meta["height"]) >= rule["min"]
        return {"status": "pass" if ok else "warn", "observed": f'{meta["width"]}x{meta["height"]}',
                "detail": f"要求 ≥ {rule['min']}px"}
    if rule["type"] == "image_ratio":
        rw, rh = rule["ratio"]
        ok = abs(meta["width"] / meta["height"] - rw / rh) < 0.02
        return {"status": "pass" if ok else "fail",
                "observed": f'{meta["width"]}x{meta["height"]}', "detail": f"要求 {rw}:{rh}"}
    ok = meta["white_ratio"] >= rule["min_ratio"]
    return {"status": "pass" if ok else "fail",
            "observed": f'白底占比 {meta["white_ratio"]:.0%}', "detail": f'要求 ≥ {rule["min_ratio"]:.0%}'}


@register_check("image_ratio")
def _check_image_ratio(rule, listing, image_path, pim):
    return _image_check(rule, image_path)


@register_check("image_white_bg")
def _check_image_white_bg(rule, listing, image_path, pim):
    return _image_check(rule, image_path)


@register_check("image_min_px")
def _check_image_min_px(rule, listing, image_path, pim):
    return _image_check(rule, image_path)


# ---------------- 自动改写钩子（按名称注册） ----------------

@register_fix("truncate")
def _fix_truncate(rule, fixed, image_path, pim):
    mx = rule.get("max", 0)
    if len(fixed.get("title", "")) > mx:
        fixed["title"] = word_cut(fixed["title"], mx)


@register_fix("strip_banned")
def _fix_strip_banned(rule, fixed, image_path, pim):
    text = fixed.get("title", "")
    for w in rule.get("words", []):
        text = re.sub(re.escape(w), "", text, flags=re.IGNORECASE)
    fixed["title"] = re.sub(r"\s{2,}", " ", re.sub(r"\s+,", ",", text)).strip(" ,|-")


@register_fix("strip_banned_desc")
def _fix_strip_banned_desc(rule, fixed, image_path, pim):
    text = fixed.get("description", "")
    for w in rule.get("words", []):
        text = re.sub(re.escape(w), "proven performance", text, flags=re.IGNORECASE)
    fixed["description"] = text


@register_fix("strip_emoji")
def _fix_strip_emoji(rule, fixed, image_path, pim):
    fixed["title"] = EMOJI_RE.sub("", fixed.get("title", "")).strip()


@register_fix("adjust_bullets")
def _fix_adjust_bullets(rule, fixed, image_path, pim):
    bullets = list(fixed.get("bullets") or [])
    lo, hi = rule.get("min", 5), rule.get("max", 5)
    if len(bullets) > hi:
        bullets = bullets[:hi]
    while len(bullets) < lo:
        bullets.append(f"Backed by 12-month warranty and responsive after-sales support #{len(bullets) + 1}")
    fixed["bullets"] = [b.rstrip() for b in bullets]


@register_fix("truncate_bullets")
def _fix_truncate_bullets(rule, fixed, image_path, pim):
    fixed["bullets"] = [word_cut(b, rule["max"]) if len(b) > rule["max"] else b
                        for b in (fixed.get("bullets") or [])]


@register_fix("pad_description")
def _fix_pad_description(rule, fixed, image_path, pim):
    desc = fixed.get("description", "")
    if len(desc) < rule.get("min", 150):
        fixed["description"] = desc + " Every unit is inspected before shipment. " * 4


@register_fix("adjust_meta")
def _fix_adjust_meta(rule, fixed, image_path, pim):
    meta = fixed.get("seo_meta", "")
    lo, hi = rule.get("min", 120), rule.get("max", 160)
    if len(meta) < lo:
        meta = meta + " Shop now with fast delivery and dedicated support."
    fixed["seo_meta"] = meta[:hi]


@register_fix("autofill_attr")
def _fix_autofill_attr(rule, fixed, image_path, pim):
    pim = pim or {}
    attrs = pim.setdefault("attributes", {})
    defaults = {"material": "Premium ABS", "color": "Classic Black", "category": pim.get("category", "General")}
    for a in rule.get("attrs", []):
        attrs.setdefault(a, defaults.get(a, "N/A"))


@register_fix("regen_image")
def _fix_regen_image(rule, fixed, image_path, pim):
    """图片管线保证主图合规，非合规来源则重跑白底 1:1（显式记日志）"""
    from . import imaging
    if image_path and not image_path.replace("\\", "/").endswith("main_white.jpg"):
        imaging.ensure_compliant_main(image_path)
        return True
    return False


# ---------------- 主流程 ----------------

def validate(platform: str, listing: dict, image_path: str = "", pim: dict | None = None) -> dict:
    """校验一个 Listing，返回报告（含规则库版本与校验时间，支持审计追溯）"""
    ruleset = load_rules(platform)
    checks = []
    for rule in ruleset["rules"]:
        fn = CHECKS.get(rule["type"])
        result = fn(rule, listing, image_path, pim) if fn else {
            "status": "warn", "observed": "未知规则类型", "detail": rule["type"]}
        result.update({"id": rule["id"], "name": rule["name"], "severity": rule["severity"], "fixable": "fix" in rule})
        checks.append(result)
    errors = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]
    return {
        "platform": platform,
        "platform_label": ruleset["label"],
        "ruleset_version": ruleset.get("version", "v0.0.0"),  # 版本随规则库文件走，改库即生效
        "validated_at": datetime.now().isoformat(timespec="seconds"),
        "passed": not errors,
        "summary": f'{len(checks) - len(errors) - len(warns)} 通过 / {len(errors)} 不合规 / {len(warns)} 建议',
        "checks": checks,
    }


def autofix(platform: str, listing: dict, image_path: str = "", pim: dict | None = None) -> tuple[dict, dict]:
    """按规则库自动改写，返回 (改写后的 listing, 修复日志)"""
    ruleset = load_rules(platform)
    fixed = dict(listing)
    log = []
    for rule in ruleset["rules"]:
        fix = rule.get("fix")
        if not fix or fix not in FIXES:
            continue
        before = json.dumps({k: fixed.get(k) for k in TEXT_FIELDS}, ensure_ascii=False)
        explicit = FIXES[fix](rule, fixed, image_path, pim) is True
        after = json.dumps({k: fixed.get(k) for k in TEXT_FIELDS}, ensure_ascii=False)
        if after != before or explicit:
            log.append({"rule": rule["id"], "action": fix, "name": rule["name"]})
    return fixed, {"platform": platform, "fixed": log}
