"""ListingForge Demo — FastAPI 入口

运行:  python run.py   (或 uvicorn app.main:app --port 8000)
体验:  http://127.0.0.1:8000
"""
import base64
import shutil
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import database as db
from . import generator, imaging, rules_engine
from .samples import SAMPLES

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "data" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ListingForge · AI 智能上新引擎 Demo", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    db.init_db()


# ---------------- 元信息 ----------------

@app.get("/api/meta")
def meta():
    return {
        "mode": generator.get_mode(),
        "mode_label": "百炼实时模式 (qwen-vl-max / qwen-plus)" if generator.get_mode() == "qwen"
                      else "本地模拟模式（设置 DASHSCOPE_API_KEY 切换百炼实时模式）",
        "platforms": [{"key": p, **_platform_brief(p)} for p in rules_engine.PLATFORMS],
        "languages": [{"key": "en", "label": "英语 EN"}, {"key": "es", "label": "西语 ES"},
                      {"key": "pt", "label": "葡语 PT"}, {"key": "ar", "label": "阿语 AR"}],
    }


def _platform_brief(p):
    r = rules_engine.load_rules(p)
    return {"label": r["label"], "region": r["region"], "rule_count": len(r["rules"])}


# ---------------- 示例 & 商品录入（F1 输入层） ----------------

@app.get("/api/samples")
def samples():
    return SAMPLES


@app.post("/api/products/sample/{key}")
def create_from_sample(key: str):
    s = next((x for x in SAMPLES if x["key"] == key), None)
    if not s:
        raise HTTPException(404, "示例不存在")
    img_src = ROOT / "assets" / s["image"]
    dest_dir = UPLOADS / "raw"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"sample_{key}.png"
    if img_src.exists():
        shutil.copy(img_src, dest)
    product = db.create_product(s["name"], s["category"], s["features"], s["price"],
                                s["target_market"], str(dest))
    return product


@app.post("/api/products")
async def create_product(name: str = Form(...), category: str = Form(""),
                         features: str = Form(""), price: float = Form(0),
                         target_market: str = Form(""), image: UploadFile = File(None)):
    feats = [f.strip() for f in re_split(features) if f.strip()]
    image_path = ""
    if image is not None and image.filename:
        dest_dir = UPLOADS / "raw"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"upload_{int(time.time())}_{image.filename}"
        with open(dest, "wb") as f:
            f.write(await image.read())
        image_path = str(dest)
    elif (ROOT / "assets" / "default_product.png").exists():
        image_path = str(ROOT / "assets" / "default_product.png")
    return db.create_product(name, category, feats, price, target_market, image_path)


def re_split(s: str):
    return s.replace("；", ";").replace("\n", ";").split(";")


def _main_image(p: dict) -> str:
    """规则校验使用图片管线的白底主图产物（而非原始上传图）"""
    cand = UPLOADS / str(p["id"]) / "images" / "main_white.jpg"
    return str(cand) if cand.exists() else (p.get("image_path") or "")


# ---------------- F1 结构化 ----------------

@app.post("/api/products/{pid}/structure")
def structure(pid: int):
    p = db.get_product(pid)
    if not p:
        raise HTTPException(404, "商品不存在")
    image_b64 = None
    if p.get("image_path") and Path(p["image_path"]).exists():
        image_b64 = base64.b64encode(Path(p["image_path"]).read_bytes()).decode()
    pim = generator.structure_product(p["name"], p["category"], p["features"],
                                      p["price"], p["target_market"], image_b64)
    pim.setdefault("attributes", {})["category"] = pim.get("category_en", "General")
    db.update_product(pid, pim=pim, status="structured")
    # 结构化后即产出合规主图（F3）
    images = imaging.process_product_image(p["image_path"], pid)
    return {"product": db.get_product(pid), "images": images}


# ---------------- F2 生成 ----------------

@app.post("/api/products/{pid}/generate")
def generate(pid: int, platforms: list[str] = Form(None), languages: list[str] = Form(None)):
    p = db.get_product(pid)
    if not p:
        raise HTTPException(404, "商品不存在")
    if not p.get("pim"):
        raise HTTPException(400, "请先执行 AI 结构化")
    platforms = platforms or rules_engine.PLATFORMS
    languages = languages or ["en"]
    created = []
    for platform in platforms:
        for lang in languages:
            data = generator.generate_listing(p["pim"], platform, lang)
            listing = db.create_listing(pid, platform, lang, data["title"], data["bullets"],
                                        data["description"], data.get("seo_meta", ""))
            report = rules_engine.validate(platform, listing, _main_image(p), p["pim"])
            db.update_listing(listing["id"], validation=report)
            created.append(db.get_listing(listing["id"]))
    db.update_product(pid, status="generated")
    return {"listings": created}


@app.get("/api/products/{pid}/listings")
def get_listings(pid: int):
    return db.list_listings(pid)


# ---------------- F4 校验 / 修复 ----------------

@app.get("/api/listings/{lid}/validate")
def validate(lid: int):
    l = db.get_listing(lid)
    if not l:
        raise HTTPException(404, "Listing 不存在")
    p = db.get_product(l["product_id"])
    report = rules_engine.validate(l["platform"], l, _main_image(p), p.get("pim"))
    db.update_listing(lid, validation=report)
    return report


@app.post("/api/listings/{lid}/autofix")
def autofix(lid: int):
    l = db.get_listing(lid)
    if not l:
        raise HTTPException(404, "Listing 不存在")
    p = db.get_product(l["product_id"])
    fixed, log = rules_engine.autofix(l["platform"], l, _main_image(p), p.get("pim"))
    db.update_listing(lid, title=fixed["title"], bullets=fixed["bullets"],
                      description=fixed["description"], seo_meta=fixed.get("seo_meta", ""))
    report = rules_engine.validate(l["platform"], db.get_listing(lid),
                                   _main_image(p), p.get("pim"))
    db.update_listing(lid, validation=report)
    return {"listing": db.get_listing(lid), "fix_log": log, "report": report}


# ---------------- F5 审核 ----------------

@app.put("/api/listings/{lid}")
def edit_listing(lid: int, title: str = Form(None), bullets: str = Form(None),
                 description: str = Form(None), seo_meta: str = Form(None)):
    l = db.get_listing(lid)
    if not l:
        raise HTTPException(404, "Listing 不存在")
    fields = {}
    if title is not None:
        fields["title"] = title
    if bullets is not None:
        fields["bullets"] = [b for b in re_split(bullets)]
    if description is not None:
        fields["description"] = description
    if seo_meta is not None:
        fields["seo_meta"] = seo_meta
    return db.update_listing(lid, **fields)


@app.post("/api/listings/{lid}/approve")
def approve(lid: int):
    return db.update_listing(lid, status="approved")


@app.post("/api/listings/{lid}/reject")
def reject(lid: int):
    return db.update_listing(lid, status="rejected")


# ---------------- F6 上架（模拟适配器，结构对齐官方 API） ----------------

@app.post("/api/products/{pid}/publish")
def publish(pid: int):
    p = db.get_product(pid)
    if not p:
        raise HTTPException(404, "商品不存在")
    approved = db.approved_listings_of_product(pid)
    if not approved:
        raise HTTPException(400, "没有已审核通过的 Listing，请先在审核工作台放行")
    tasks = []
    for l in approved:
        task = db.create_task(pid, l["id"], l["platform"], l["language"])
        ok, msg = fake_adapter_publish(p, l)
        db.update_task(task["id"], status="success" if ok else "failed", message=msg)
        if ok:
            db.update_listing(l["id"], status="published")
        tasks.append(db.list_tasks(pid)[-1])
    db.update_product(pid, status="published")
    return {"tasks": db.list_tasks(pid)}


def fake_adapter_publish(p: dict, l: dict) -> tuple[bool, str]:
    """模拟上架适配器。生产替换为 shopify_python_api / python-amazon-sp-api /
    速卖通 OpenAPI / TikTok Shop API 的真实调用，接口签名保持一致。"""
    time.sleep(0.3)
    listing_id = f"LF-{l['platform'].upper()[:3]}-{l['id']:04d}-{int(time.time()) % 10000}"
    return True, f"上架成功 · 平台商品 ID {listing_id}"


@app.get("/api/products/{pid}/tasks")
def tasks(pid: int):
    return db.list_tasks(pid)


# ---------------- 查询 ----------------

@app.get("/api/products")
def products():
    return db.list_products()


@app.get("/api/products/{pid}")
def product(pid: int):
    p = db.get_product(pid)
    if not p:
        raise HTTPException(404, "商品不存在")
    return p


@app.delete("/api/products/{pid}")
def delete_product(pid: int):
    p = db.get_product(pid)
    if not p:
        raise HTTPException(404)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.execute("DELETE FROM listings WHERE product_id=?", (pid,))
        conn.execute("DELETE FROM tasks WHERE product_id=?", (pid,))
    return {"ok": True}


@app.exception_handler(Exception)
def on_error(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


# 静态资源（前端工作台 + 图片）
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
app.mount("/data", StaticFiles(directory=str(ROOT / "data")), name="data")


@app.get("/")
def index():
    return FileResponse(str(ROOT / "app" / "static" / "index.html"))
