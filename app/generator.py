"""AI 文案引擎（F1 结构化 / F2 文案工厂）

双轨模式（DEMO_MODE 自动降级，保证离线可运行）：
- mock : 模板 + 规则化生成，确定性、零依赖、秒级出稿（默认）
- qwen : 阿里云百炼 DashScope OpenAI 兼容接口（qwen-vl-max / qwen-plus）
         设置环境变量 DASHSCOPE_API_KEY 后自动启用

多语言：EN 主文案 + 西/葡/阿语"本地化重写"（mock 用词库映射，qwen 模式为真重写）。
"""
import json
import os
import re

MODE = "qwen" if os.environ.get("DASHSCOPE_API_KEY") else "mock"

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
CHAT_MODEL = "qwen-plus"
VL_MODEL = "qwen-vl-max"

# ---------- 分类知识库（demo 用，真实模式由模型推断） ----------

CATEGORY_MAP = {
    "保温杯": {"en": "Insulated Water Bottle", "audience": "commuters, office workers and gym users",
               "scene": "travel, office and workout", "kw": ["insulated water bottle", "thermos", "travel mug"]},
    "水杯": {"en": "Insulated Water Bottle", "audience": "commuters and fitness users",
             "scene": "daily hydration", "kw": ["water bottle", "thermos"]},
    "耳机": {"en": "Wireless Earbuds", "audience": "commuters, students and gamers",
             "scene": "music, calls and gaming", "kw": ["wireless earbuds", "bluetooth headphones", "tws"]},
    "喂食器": {"en": "Automatic Pet Feeder", "audience": "cat and small dog owners",
               "scene": "scheduled feeding at home", "kw": ["automatic pet feeder", "cat feeder", "dog feeder"]},
    "宠物": {"en": "Pet Supplies", "audience": "pet owners", "scene": "daily pet care",
             "kw": ["pet supplies", "pet accessories"]},
}
MATERIALS = {"不锈钢": "Stainless Steel", "钢": "Stainless Steel", "硅胶": "Food-Grade Silicone",
             "abs": "Premium ABS", "陶瓷": "Ceramic", "塑料": "Food-Grade PP"}
COLORS = {"黑": "Classic Black", "白": "Pearl White", "蓝": "Ocean Blue", "粉": "Rose Pink",
          "绿": "Mint Green", "银": "Space Silver", "灰": "Space Gray"}

LANG_PACK = {
    "en": {"bullet_leads": ["SMART DESIGN", "PREMIUM QUALITY", "EASY TO USE", "WIDE APPLICATION", "WORRY-FREE BUY"],
           "titles": [], "casing": "upper"},
    "es": {"name": "español", "intro": "¡Descubre la nueva forma de {cat}! ",
           "outro": " Envío rápido y soporte dedicado. ¡Cómpralo ahora!",
           "words": {"Stainless Steel": "acero inoxidable", "Insulated Water Bottle": "botella térmica",
                     "Wireless Earbuds": "auriculares inalámbricos", "Automatic Pet Feeder": "comedero automático",
                     "Smart": "Inteligente", "Leak-Proof": "antifugas", "Portable": "portátil"}},
    "pt": {"name": "português", "intro": "Descubra a nova forma de {cat}! ",
           "outro": " Envio rápido e suporte dedicado. Compre agora!",
           "words": {"Stainless Steel": "aço inoxidável", "Insulated Water Bottle": "garrafa térmica",
                     "Wireless Earbuds": "fone de ouvido sem fio", "Automatic Pet Feeder": "alimentador automático",
                     "Smart": "Inteligente", "Leak-Proof": "à prova de vazamento", "Portable": "portátil"}},
    "ar": {"name": "العربية", "intro": "اكتشف الطريقة الجديدة لـ{cat}! ",
           "outro": " توصيل سريع ودعم مخصص. اشترِ الآن!",
           "words": {"Stainless Steel": "ستانلس ستيل", "Insulated Water Bottle": "زجاجة حرارية",
                     "Wireless Earbuds": "سماعات لاسلكية", "Automatic Pet Feeder": "مغذية الحيوانات الأليفة",
                     "Smart": "ذكي", "Leak-Proof": "مقاوم للتسرب", "Portable": "محمول"}},
}
PLATFORM_SPEC = {
    "amazon": {"label": "亚马逊", "title_max": 200, "bullets": 5},
    "aliexpress": {"label": "速卖通", "title_max": 128, "bullets": 5},
    "tiktok_shop": {"label": "TikTok Shop", "title_max": 90, "bullets": 4},
    "shopify": {"label": "Shopify", "title_max": 70, "bullets": 4},
}

# ---------- F1 结构化 ----------

def structure_product_mock(name: str, category: str, features: list, price: float,
                           target_market: str) -> dict:
    cat_key = next((k for k in CATEGORY_MAP if k in f"{name}{category}"), None)
    cat = CATEGORY_MAP.get(cat_key, {"en": category or "Lifestyle Product",
                                     "audience": target_market or "global buyers",
                                     "scene": "daily use",
                                     "kw": [(category or "product").lower()]})
    text = f"{name} {' '.join(features)}"
    attrs = {}
    for zh, en in MATERIALS.items():
        if zh.lower() in text.lower():
            attrs["material"] = en
            break
    color_text = text.replace("蓝牙", "").replace("蓝光", "")  # 避免「蓝牙」误判为蓝色
    for zh, en in COLORS.items():
        if zh in color_text:
            attrs["color"] = en
            break
    m = re.search(r"(\d{2,4})\s*ml", text, re.I)
    if m:
        attrs["capacity"] = f"{m.group(1)}ml"
    attrs.setdefault("color", "Classic Black")
    attrs.setdefault("material", "Premium ABS")
    attrs.setdefault("category", cat["en"])
    selling_points = [_benefit(f) for f in features]
    keywords = list(dict.fromkeys(cat["kw"] + [w.lower() for w in re.findall(r"[A-Za-z]{4,}", text)[:6]]))[:8]
    return {
        "product_name": name, "category": category or cat_key or "日用百货", "category_en": cat["en"],
        "attributes": attrs, "selling_points": selling_points,
        "keywords": keywords, "target_audience": target_market or cat["audience"],
        "use_scenarios": [cat["scene"]], "price_usd": price,
        "source": "mock",
    }


def _benefit(feature: str) -> str:
    """中文卖点 -> 英文利益点（demo 词库映射；qwen 模式由模型生成）"""
    table = [
        ("温度显示", "Smart LED temperature display lets you check drink temp at a glance"),
        ("保温", "Vacuum-insulated: keeps drinks cold 24h / hot 12h"),
        ("保冷", "Double-wall vacuum keeps beverages cold up to 24 hours"),
        ("无线充电", "Wireless charging case delivers 24h total playtime"),
        ("蓝牙5", "Bluetooth 5.3 ensures stable pairing and low latency"),
        ("降噪", "Active noise cancellation for immersive audio in noisy commutes"),
        ("定时", "Programmable timer schedules up to 6 meals per day"),
        ("APP", "App remote control for feeding anywhere, anytime"),
        ("防漏", "Leak-proof lock design fits safely in any bag"),
        ("便携", "Compact and portable for travel, gym and office"),
        ("大容量", "Large capacity design reduces refill frequency"),
        ("快充", "Fast-charge technology: 10 min charging = 2h playback"),
        ("防水", "IPX5 waterproof rating withstands sweat and rain"),
        ("夜灯", "Built-in night light for late-night feeding"),
    ]
    for zh, en in table:
        if zh in feature:
            return en
    return f"{feature} — engineered for reliable everyday performance"


# ---------- F2 文案生成（mock） ----------

def _short(s: str, n: int) -> str:
    """语义截断：先取逗号前的主短语，再按词边界截断，避免残句"""
    s = (s or "").rstrip(".").replace("：", ",").replace(":", ",")
    s = s.split(",")[0].strip().rstrip(",;-–— ")
    if len(s) <= n:
        return s
    return s[:n].rsplit(" ", 1)[0].rstrip(",;-–— ")


def _audience_en(pim: dict) -> str:
    """EN 文案里的人群词（中文输入自动回退，避免中英混排）"""
    aud = pim.get("target_audience") or "everyday users"
    return "friends and family" if re.search(r"[\u4e00-\u9fff]", str(aud)) else aud


def _title_en(pim: dict, platform: str) -> str:
    name_en = pim.get("category_en", "Product")
    attrs = pim.get("attributes", {})
    material, color = attrs.get("material", ""), attrs.get("color", "")
    sp = pim.get("selling_points", [])
    f1 = _short(sp[0], 32) if sp else "Smart Design"
    f2 = _short(sp[1], 26) if len(sp) > 1 else "Portable"
    scene = pim.get("use_scenarios", ["daily use"])[0]
    if platform == "amazon":
        t = f"{name_en} {material} {color} with {f1}, {f2} for {scene}"
    elif platform == "aliexpress":
        kw = [k for k in pim.get("keywords", []) if k.lower() not in name_en.lower()][:1]
        t = f"{name_en} {material} {color} {f1} {' '.join(kw)}".strip()
    elif platform == "tiktok_shop":
        t = f"{name_en} | {f1} — {f2}"
    else:
        t = f"Aurora {name_en} — {f1}"
    mx = PLATFORM_SPEC[platform]["title_max"]
    if len(t) > mx:  # 词边界安全截断
        t = t[:mx].rsplit(" ", 1)[0].rstrip(",;-–—:")
    return re.sub(r"\s{2,}", " ", t).strip()


def _bullets_en(pim: dict, n: int) -> list:
    leads = LANG_PACK["en"]["bullet_leads"]
    sp = pim.get("selling_points", [])
    aud = _audience_en(pim)
    bullets = []
    for i in range(n):
        lead = leads[i % len(leads)]
        body = sp[i] if i < len(sp) else f"Ideal gift for {aud}"
        bullets.append(f"{lead}: {body}.")
    return bullets


def _description_en(pim: dict) -> str:
    name_en = pim.get("category_en", "Product")
    sp = pim.get("selling_points", [])
    scene = pim.get("use_scenarios", ["daily use"])[0]
    if sp:
        hook = f"Meet the {name_en} — {sp[0].lower().rstrip('.')}, designed for {scene}."
        body = " ".join(x.rstrip(".") + "." for x in sp[1:5])
    else:
        hook = f"Meet the {name_en}, designed for {scene}."
        body = "Quality you can trust."
    cta = f"Perfect for {_audience_en(pim)}. Add it to your cart and upgrade your daily routine today."
    return " ".join([hook, body, cta])


def _localized_listing(pim: dict, platform: str, language: str) -> dict:
    """本地化重写：优先命中类目文案库（地道重写），未命中则词库映射 + 本地化框架改写"""
    spec = PLATFORM_SPEC[platform]
    lib = LOCALIZED_LIBRARY.get(pim.get("category_en", ""), {}).get(language)
    if lib:
        return {"title": lib["title"][: spec["title_max"]].rstrip(),
                "bullets": lib["bullets"][: spec["bullets"]],
                "description": lib["desc"], "seo_meta": lib.get("seo") or lib["desc"][:155].strip()}
    pack = LANG_PACK.get(language, LANG_PACK["es"])
    words = pack.get("words", {})

    def tx(s: str) -> str:
        for k, v in words.items():
            s = re.sub(re.escape(k), v, s, flags=re.IGNORECASE)
        return s

    title = tx(_title_en(pim, platform))[: spec["title_max"]].rstrip()
    bullets = [tx(b) for b in _bullets_en(pim, spec["bullets"])]
    desc = tx(_description_en(pim))
    if language == "ar":
        description = f"{pack['intro'].format(cat=pim.get('category_en', 'product'))} {desc}{pack['outro']}"
    else:
        description = f"{pack['intro'].format(cat=pim.get('category_en', 'product'))}{desc}{pack['outro']}"
    return {"title": title, "bullets": bullets, "description": description,
            "seo_meta": description[:155].strip()}


# 本地化文案库（非直译：按小语种表达习惯重写；qwen 模式下由模型真重写）
LOCALIZED_LIBRARY = {
    "Insulated Water Bottle": {
        "es": {
            "title": "Botella Térmica Inteligente 500ml de Acero Inoxidable con Pantalla LED, Antifugas y Portátil",
            "bullets": [
                "PANTALLA LED INTELIGENTE: consulta la temperatura de tu bebida con solo tocar la tapa.",
                "ACERO INOXIDABLE: doble pared de vacío que mantiene frío 24 h y caliente 12 h.",
                "CIERRE ANTIFUGAS: seguro para llevar en cualquier bolso o mochila.",
                "DISEÑO PORTÁTIL: encaja en portavasos de coche, perfecta para oficina, gimnasio y viajes.",
                "REGALO IDEAL: caja premium lista para regalar a familiares y amigos."],
            "desc": "La botella térmica inteligente que mantiene tu bebida a la temperatura perfecta: pantalla LED táctil, acero inoxidable de doble pared y cierre antifugas, para oficina, gimnasio y viajes. ¡Pídelo hoy con envío rápido y soporte dedicado!",
            "seo": "Botella térmica inteligente de acero inoxidable con pantalla LED. Frío 24 h, caliente 12 h. Envío rápido."},
        "pt": {
            "title": "Garrafa Térmica Inteligente 500ml de Aço Inoxidável com Painel LED, à Prova de Vazamentos",
            "bullets": [
                "PAINEL LED INTELIGENTE: verifique a temperatura da bebida com um toque.",
                "AÇO INOXIDÁVEL: parede dupla a vácuo mantém gelado 24 h e quente 12 h.",
                "FECHAMENTO ANTI-VAZAMENTO: pode levar na mochila sem preocupações.",
                "DESIGN PORTÁTIL: cabe no porta-copos do carro, ideal para escritório, academia e viagens.",
                "PRESENTE PERFEITO: embalagem premium pronta para presentear."],
            "desc": "A garrafa térmica inteligente que mantém sua bebida na temperatura ideal: painel LED de toque, aço inoxidável de parede dupla e fechamento à prova de vazamentos, para escritório, academia e viagens. Compre agora com envio rápido e suporte dedicado!",
            "seo": "Garrafa térmica inteligente de aço inoxidable com painel LED. Gelado 24 h, quente 12 h. Envio rápido."},
        "ar": {
            "title": "زجاجة حرارية ذكية 500ml من الستانلس ستيل مع شاشة LED، مقاومة للتسرب",
            "bullets": [
                "شاشة LED ذكية: تعرف على درجة حرارة مشروبك بلمسة واحدة.",
                "ستانلس ستيل بجدار مزدوج: يحافظ على البرودة 24 ساعة والحرارة 12 ساعة.",
                "قفل مقاوم للتسرب: آمنة تماماً داخل حقيبتك.",
                "تصميم محمول: مناسبة لحامل أكواب السيارة والمكتب والجيم والسفر.",
                "هدية مثالية: علبة فاخرة جاهزة للإهداء."],
            "desc": "زجاجة حرارية ذكية تحافظ على مشروبك بالدرجة المثالية، مع شاشة LED لمسية وستانلس ستيل بجدار مزدوج وقفل مقاوم للتسرب — للمكتب والجيم والسفر. اطلبها الآن مع توصيل سريع ودعم مخصص!",
            "seo": "زجاجة حرارية ذكية من الستانلس ستيل مع شاشة LED. باردة 24 ساعة، ساخنة 12 ساعة. توصيل سريع."},
    },
    "Wireless Earbuds": {
        "es": {
            "title": "Auriculares Inalámbricos con Cancelación Activa de Ruido, Bluetooth 5.3 y Carga Rápida",
            "bullets": [
                "CANCELACIÓN ACTIVA DE RUIDO: sumérgete en tu música incluso en el metro más concurrido.",
                "BLUETOOTH 5.3: emparejamiento estable y baja latencia para llamadas y juegos.",
                "CARGA RÁPIDA: 10 minutos de carga te dan 2 horas de reproducción.",
                "IPX5 RESISTENTE AL AGUA: aguanta sudor y lluvia sin problemas.",
                "HASTA 24 H DE AUTONOMÍA: con el estuche de carga inalámbrica."],
            "desc": "Auriculares inalámbricos con cancelación activa de ruido y Bluetooth 5.3, con carga rápida y estuche inalámbrico para hasta 24 horas de música. ¡Pídelos hoy con envío rápido y soporte dedicado!",
            "seo": "Auriculares inalámbricos con cancelación de ruido, Bluetooth 5.3 y 24 h de autonomía. Envío rápido."},
        "pt": {
            "title": "Fone de Ouvido Sem Fio com Cancelamento Ativo de Ruído, Bluetooth 5.3 e Carga Rápida",
            "bullets": [
                "CANCELAMENTO ATIVO DE RUÍDO: mergulhe na sua música mesmo no metrô lotado.",
                "BLUETOOTH 5.3: pareamento estável e baixa latência para chamadas e jogos.",
                "CARREGAMENTO RÁPIDO: 10 minutos na tomada rendem 2 horas de reprodução.",
                "IPX5 À PROVA D'ÁGUA: aguenta suor e chuva sem problemas.",
                "ATÉ 24 H DE BATERIA: com o estojo de carregamento sem fio."],
            "desc": "Fone de ouvido sem fio com cancelamento ativo de ruído e Bluetooth 5.3, com carga rápida e estojo sem fio para até 24 horas de música. Compre agora com envio rápido e suporte dedicado!",
            "seo": "Fone sem fio com cancelamento de ruído, Bluetooth 5.3 e 24 h de bateria. Envio rápido."},
        "ar": {
            "title": "سماعات لاسلكية بخاصية إلغاء الضوضاء النشط، بلوتوث 5.3 وشحن سريع",
            "bullets": [
                "إلغاء الضوضاء النشط: استمتع بموسيقاك حتى في أكثر وسائل النقل ازدحاماً.",
                "بلوتوث 5.3: اتصال مستقر وزمن استجابة منخفض للمكالمات والألعاب.",
                "شحن سريع: 10 دقائق شحن تمنحك ساعتين تشغيل.",
                "مقاومة للماء IPX5: تتحمل العرق والمطر.",
                "حتى 24 ساعة تشغيل: مع علبة الشحن اللاسلكية."],
            "desc": "سماعات لاسلكية بإلغاء الضوضاء النشط وبلوتوث 5.3، مع شحن سريع وعلبة شحن لاسلكية تمنحك حتى 24 ساعة استماع. اطلبها الآن مع توصيل سريع ودعم مخصص!",
            "seo": "سماعات لاسلكية بإلغاء الضوضاء وبلوتوث 5.3 و24 ساعة تشغيل. توصيل سريع."},
    },
    "Automatic Pet Feeder": {
        "es": {
            "title": "Comedero Automático para Gatos y Perros 4L con Programador de Horas y Luz Nocturna",
            "bullets": [
                "APP REMOTA: programa hasta 6 comidas al día desde tu móvil, estés donde estés.",
                "PORCIONES PRECISAS: dosificación exacta para controlar la dieta de tu mascota.",
                "LUZ NOCTURNA: alimentación nocturna sin molestar a tu gato.",
                "DEPÓSITO DE 4L: menos reabastecimientos, ideal para viajes cortos.",
                "FÁCIL DE LIMPIAR: piezas desmontables aptas para lavavajillas."],
            "desc": "Comedero automático de 4 L con control por APP para gatos y perros: hasta 6 comidas programadas, porciones precisas y luz nocturna integrada. ¡Pídelo hoy con envío rápido y soporte dedicado!",
            "seo": "Comedero automático 4L con APP, 6 comidas programables y luz nocturna. Envío rápido."},
        "pt": {
            "title": "Alimentador Automático para Gatos e Cães 4L com Programador de Horários e Luz Noturna",
            "bullets": [
                "APP REMOTO: programe até 6 refeições por dia pelo celular, de onde estiver.",
                "PORÇÕES PRECISAS: dosagem exata para controlar a dieta do seu pet.",
                "LUZ NOTURNA: alimentação noturna sem assustar seu gato.",
                "DEPÓSITO DE 4L: menos reabastecimentos, ideal para viagens curtas.",
                "FÁCIL DE LIMPAR: peças removíveis que podem ir à lava-louças."],
            "desc": "Alimentador automático de 4 L com controle por APP para gatos e cães: até 6 refeições programadas, porções precisas e luz noturna integrada. Compre agora com envio rápido e suporte dedicado!",
            "seo": "Alimentador automático 4L com APP, 6 refeições programáveis e luz noturna. Envio rápido."},
        "ar": {
            "title": "مغذية الحيوانات الأليفة الأوتوماتيكية 4L للقطط والكلاب مع مؤقت ومصباح ليلي",
            "bullets": [
                "تحكم عبر التطبيق: برمجة حتى 6 وجبات يومياً من هاتفك أينما كنت.",
                "حصص دقيقة: جرعات مضبوطة لضبط نظام طعام حيوانك.",
                "مصباح ليلي: تغذية ليلية دون إزعاج قطك.",
                "خزان 4 لتر: إعادة تعبئة أقل، مثالي للسفر القصير.",
                "سهلة التنظيف: أجزاء قابلة للفصل وآمنة في غسالة الأطباق."],
            "desc": "مغذية أوتوماتيكية بسعة 4 لتر مع تحكم عبر التطبيق للقطط والكلاب، تدعم حتى 6 وجبات مجدولة بحصص دقيقة ومصباح ليلي مدمج. اطلبها الآن مع توصيل سريع ودعم مخصص!",
            "seo": "مغذية أوتوماتيكية 4 لتر مع تطبيق و6 وجبات قابلة للبرمجة. توصيل سريع."},
    },
}


def generate_listing_mock(pim: dict, platform: str, language: str = "en") -> dict:
    spec = PLATFORM_SPEC[platform]
    n_bullets = spec["bullets"]
    title = _title_en(pim, platform)
    bullets = _bullets_en(pim, n_bullets)
    description = _description_en(pim)
    seo_meta = f"Shop {pim.get('category_en', 'the product')} with {pim.get('attributes', {}).get('material', 'premium')} build. " \
               f"{pim.get('selling_points', ['Great quality'])[0][:100]}"
    if language != "en":
        loc = _localized_listing(pim, platform, language)
        title, bullets, description, seo_meta = loc["title"], loc["bullets"], loc["description"], loc["seo_meta"]
    if platform == "aliexpress" and language == "en":
        # 模拟"原始 AI 稿件"常见促销词违规，由规则引擎拦截并自动改写（演示规则引擎兜底价值）
        title = f"Hot Sale {title} Free Shipping"
    return {"title": title, "bullets": bullets, "description": description, "seo_meta": seo_meta,
            "platform": platform, "language": language, "source": "mock"}


# ---------- 百炼真实模式 ----------

def _dashscope_chat(messages: list, model: str = CHAT_MODEL, image_b64: str | None = None) -> str:
    import base64
    import httpx
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    assert api_key, "DASHSCOPE_API_KEY 未设置"
    if image_b64:
        messages = [dict(messages[0])]
        messages[0] = {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            {"type": "text", "text": messages[0]["content"]},
        ]}
    resp = httpx.post(
        DASHSCOPE_BASE,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "temperature": 0.4},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", text)
    return json.loads(m.group(0)) if m else {}


def structure_product_real(name: str, category: str, features: list, price: float,
                           target_market: str, image_b64: str | None = None) -> dict:
    prompt = (
        "你是跨境电商商品数据结构化专家。根据商品信息"
        f"(名称:{name}; 类目:{category}; 卖点:{features}; 价格:{price}; 目标市场:{target_market})"
        "输出 JSON：{product_name, category, category_en, attributes:{material,color,...}, "
        "selling_points(英文利益点数组), keywords, target_audience, use_scenarios}。只输出 JSON。"
    )
    if image_b64:
        prompt = "识别商品图片并结合以下信息：" + prompt
        text = _dashscope_chat([{"role": "user", "content": prompt}], VL_MODEL, image_b64)
    else:
        text = _dashscope_chat([{"role": "user", "content": prompt}])
    pim = _extract_json(text)
    pim["source"] = f"百炼 {VL_MODEL if image_b64 else CHAT_MODEL}"
    return pim


def generate_listing_real(pim: dict, platform: str, language: str = "en") -> dict:
    from .rules_engine import load_rules
    spec = PLATFORM_SPEC[platform]
    rules = load_rules(platform)
    constraint = "; ".join(
        f'{r["name"]}' for r in rules["rules"] if r["type"].startswith(("length", "banned", "list_count")))
    prompt = (
        f"你是资深跨境电商 Listing 文案专家。基于商品结构化数据 {json.dumps(pim, ensure_ascii=False)[:1500]}，"
        f"为平台 {spec['label']} 生成 {language} 语言 Listing。硬性规则：{constraint}。"
        f"输出 JSON: {{title(≤{spec['title_max']}字符), bullets({spec['bullets']}条), description, seo_meta}}。只输出 JSON。"
    )
    data = _extract_json(_dashscope_chat([{"role": "user", "content": prompt}]))
    data.update({"platform": platform, "language": language, "source": f"百炼 {CHAT_MODEL}"})
    return data


# ---------- 对外统一入口 ----------

def get_mode() -> str:
    return MODE


def structure_product(name, category, features, price, target_market, image_b64=None) -> dict:
    if MODE == "qwen":
        try:
            return structure_product_real(name, category, features, price, target_market, image_b64)
        except Exception as e:  # 真实模式失败自动降级，保证 Demo 可用
            pim = structure_product_mock(name, category, features, price, target_market)
            pim["source"] = f"mock（百炼调用失败: {type(e).__name__}）"
            return pim
    return structure_product_mock(name, category, features, price, target_market)


def generate_listing(pim: dict, platform: str, language: str = "en") -> dict:
    if MODE == "qwen":
        try:
            return generate_listing_real(pim, platform, language)
        except Exception:
            pass
    return generate_listing_mock(pim, platform, language)
