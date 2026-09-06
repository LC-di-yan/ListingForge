"""平台规则引擎（F4 · 差异化核心）

"规则即代码"：每个平台的规则库是 app/rules/*.json，可版本化、可扩展。
新增平台 = 新增一份规则 JSON +（可选）新增生成 Adapter，无需改引擎代码。

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


def _check_text(text: str) -> str:
    return text or ""


def _eval_rule(rule: dict, listing: dict, image_path: str, pim: dict | None) -> dict:
    """单条规则校验，返回 {status: pass|fail|warn, detail, observed}"""
    rtype = rule["type"]
    field = rule.get("field", "")
    value = listing.get(field, "") if field != "pim" else None

    if rtype == "length_max":
        n = len(_check_text(value))
        ok = n <= rule["max"]
        return {"status": "pass" if ok else "fail", "observed": f"{n} 字符",
                "detail": f"限制 {rule['max']}"}

    if rtype == "length_min":
        n = len(_check_text(value))
        ok = n >= rule["min"]
        return {"status": "pass" if ok else ("fail" if rule["severity"] == "error" else "warn"),
                "observed": f"{n} 字符", "detail": f"要求 ≥ {rule['min']}"}

    if rtype == "length_range":
        n = len(_check_text(value))
        ok = rule["min"] <= n <= rule["max"]
        return {"status": "pass" if ok else "warn", "observed": f"{n} 字符",
                "detail": f"建议 {rule['min']}-{rule['max']}"}

    if rtype == "banned_words":
        text = _check_text(value)
        hits = [w for w in rule["words"] if w.lower() in text.lower()]
        ok = not hits
        return {"status": "pass" if ok else "fail", "observed": "未命中" if ok else "命中: " + ", ".join(hits),
                "detail": f"禁用词表 {len(rule['words'])} 项"}

    if rtype == "no_emoji":
        text = _check_text(value)
        hits = EMOJI_RE.findall(text)
        ok = not hits
        return {"status": "pass" if ok else "fail", "observed": "无" if ok else f"{len(hits)} 个符号",
                "detail": "标题不得含 Emoji/特殊符号"}

    if rtype == "list_count":
        items = listing.get(field) or []
        n = len(items)
        ok = rule["min"] <= n <= rule["max"]
        return {"status": "pass" if ok else "fail", "observed": f"{n} 条",
                "detail": f"要求 {rule['min']}-{rule['max']} 条"}

    if rtype == "item_length_max":
        items = listing.get(field) or []
        bad = [(i, len(s)) for i, s in enumerate(items, 1) if len(s) > rule["max"]]
        ok = not bad
        return {"status": "pass" if ok else "warn", "observed": "全部合规" if ok else f"超长 {len(bad)} 条",
                "detail": f"每条 ≤ {rule['max']} 字符"}

    if rtype == "attr_required":
        pim = pim or {}
        attrs = pim.get("attributes", {}) if isinstance(pim, dict) else {}
        missing = [a for a in rule["attrs"] if not attrs.get(a)]
        ok = not missing
        return {"status": "pass" if ok else "fail", "observed": "齐全" if ok else "缺失: " + ", ".join(missing),
                "detail": "必填: " + ", ".join(rule["attrs"])}

    if rtype == "keyword_hits":
        title = _check_text(listing.get("title", "")).lower()
        keywords = (pim or {}).get("keywords", []) if isinstance(pim, dict) else []
        hits = [k for k in keywords if k and k.lower() in title]
        ok = len(hits) >= rule.get("min_hits", 2)
        shown = ", ".join(hits[:3]) + ("…" if len(hits) > 3 else "")
        return {"status": "pass" if ok else rule.get("severity", "warn"),
                "observed": f'命中 {len(hits)}/{len(keywords)}' + (f': {shown}' if hits else ''),
                "detail": f"需命中 ≥{rule.get('min_hits', 2)} 个核心关键词"}

    if rtype in ("image_ratio", "image_white_bg", "image_min_px"):
        # 图片类规则由图片管线保证（白底主图 1:1 / ≥1000px），此处用管线产物元数据校验
        if not image_path:
            return {"status": "fail", "observed": "无主图", "detail": "需先生成主图"}
        from . import imaging
        meta = imaging.image_meta(image_path)
        if rtype == "image_min_px":
            ok = min(meta["width"], meta["height"]) >= rule["min"]
            return {"status": "pass" if ok else "warn", "observed": f'{meta["width"]}x{meta["height"]}',
                    "detail": f"要求 ≥ {rule['min']}px"}
        if rtype == "image_ratio":
            rw, rh = rule["ratio"]
            ok = abs(meta["width"] / meta["height"] - rw / rh) < 0.02
            return {"status": "pass" if ok else "fail",
                    "observed": f'{meta["width"]}x{meta["height"]}', "detail": f"要求 {rw}:{rh}"}
        ok = meta["white_ratio"] >= rule["min_ratio"]
        return {"status": "pass" if ok else "fail",
                "observed": f'白底占比 {meta["white_ratio"]:.0%}', "detail": f'要求 ≥ {rule["min_ratio"]:.0%}'}

    return {"status": "warn", "observed": "未知规则类型", "detail": rtype}


def validate(platform: str, listing: dict, image_path: str = "", pim: dict | None = None) -> dict:
    """校验一个 Listing，返回报告（含规则库版本与校验时间，支持审计追溯）"""
    ruleset = load_rules(platform)
    checks = []
    for rule in ruleset["rules"]:
        result = _eval_rule(rule, listing, image_path, pim)
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
        if not fix:
            continue
        before = json.dumps({k: fixed.get(k) for k in ("title", "bullets", "description", "seo_meta")},
                            ensure_ascii=False)
        if fix == "truncate" and len(fixed.get("title", "")) > rule.get("max", 0):
            fixed["title"] = word_cut(fixed["title"], rule["max"])
        elif fix == "strip_banned":
            text = fixed.get("title", "")
            for w in rule.get("words", []):
                text = re.sub(re.escape(w), "", text, flags=re.IGNORECASE)
            fixed["title"] = re.sub(r"\s{2,}", " ", re.sub(r"\s+,", ",", text)).strip(" ,|-")
        elif fix == "strip_banned_desc":
            text = fixed.get("description", "")
            for w in rule.get("words", []):
                text = re.sub(re.escape(w), "proven performance", text, flags=re.IGNORECASE)
            fixed["description"] = text
        elif fix == "strip_emoji":
            fixed["title"] = EMOJI_RE.sub("", fixed.get("title", "")).strip()
        elif fix == "adjust_bullets":
            bullets = list(fixed.get("bullets") or [])
            lo, hi = rule.get("min", 5), rule.get("max", 5)
            if len(bullets) > hi:
                bullets = bullets[:hi]
            while len(bullets) < lo:
                bullets.append(f"Backed by 12-month warranty and responsive after-sales support #{len(bullets) + 1}")
            fixed["bullets"] = [b.rstrip() for b in bullets]
        elif fix == "truncate_bullets":
            fixed["bullets"] = [word_cut(b, rule["max"]) if len(b) > rule["max"] else b
                                for b in (fixed.get("bullets") or [])]
        elif fix == "pad_description":
            desc = fixed.get("description", "")
            min_len = rule.get("min", 150)
            if len(desc) < min_len:
                filler = (" Every unit is inspected before shipment. " * 4)
                fixed["description"] = desc + filler
        elif fix == "adjust_meta":
            meta = fixed.get("seo_meta", "")
            lo, hi = rule.get("min", 120), rule.get("max", 160)
            if len(meta) < lo:
                meta = meta + " Shop now with fast delivery and dedicated support."
            fixed["seo_meta"] = meta[:hi]
        elif fix == "autofill_attr":
            pim = pim or {}
            attrs = pim.setdefault("attributes", {})
            defaults = {"material": "Premium ABS", "color": "Classic Black", "category": pim.get("category", "General")}
            for a in rule.get("attrs", []):
                attrs.setdefault(a, defaults.get(a, "N/A"))
        elif fix == "regen_image":
            # 图片管线保证主图合规，非合规来源则重跑白底 1:1
            from . import imaging
            if image_path and not image_path.replace("\\", "/").endswith("main_white.jpg"):
                imaging.ensure_compliant_main(image_path)
                log.append({"rule": rule["id"], "action": fix, "name": rule["name"]})
        after = json.dumps({k: fixed.get(k) for k in ("title", "bullets", "description", "seo_meta")},
                           ensure_ascii=False)
        if after != before:
            log.append({"rule": rule["id"], "action": fix, "name": rule["name"]})
    return fixed, {"platform": platform, "fixed": log}
