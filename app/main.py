"""ListingForge Demo — FastAPI 入口

运行:  python run.py   (或 uvicorn app.main:app --port 8000)
体验:  http://127.0.0.1:8000
"""
import base64
import logging
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
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

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
GENERATE_WORKERS = 4  # 并发生成上限（兼顾 DashScope 限流）

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("listingforge")
_pool = ThreadPoolExecutor(max_workers=GENERATE_WORKERS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    log.info("ListingForge 启动完成 · 模式=%s · 体验地址 http://127.0.0.1:8000", generator.get_mode())
    yield  # 线程池随进程退出回收，不做 shutdown（支持多次 startup 的测试场景）


app = FastAPI(title="ListingForge · AI 智能上新引擎 Demo", version="1.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
    return db.create_product(s["name"], s["category"], s["features"], s["price"],
                             s["target_market"], str(dest))


@app.post("/api/products")
async def create_product(name: str = Form(...), category: str = Form(""),
                         features: str = Form(""), price: float = Form(0),
                         target_market: str = Form(""), image: UploadFile = File(None)):
    feats = [f.strip() for f in re_split(features) if f.strip()]
    image_path = ""
    if image is not None and image.filename:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(400, "仅支持 PNG / JPG / WebP 图片")
        safe_name = Path(image.filename).name  # 去除路径成分，防穿越
        if not safe_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            raise HTTPException(400, "图片扩展名必须为 png / jpg / jpeg / webp")
        data = await image.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "图片不能超过 8MB")
        dest_dir = UPLOADS / "raw"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"upload_{uuid.uuid4().hex[:8]}_{safe_name}"  # uuid 防同秒同名覆盖
        with open(dest, "wb") as f:
            f.write(data)
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


def _product_images(p: dict) -> dict | None:
    """商品图片产物（web 路径，前端可直接使用；不存在返回 None）"""
    d = UPLOADS / str(p["id"]) / "images"
    if not (d / "main_white.jpg").exists():
        return None
    return {
        "main": f"/data/uploads/{p['id']}/images/main_white.jpg",
        "scene": f"/data/uploads/{p['id']}/images/scene.jpg",
        "variants": {k: f"/data/uploads/{p['id']}/images/variant_{k}.jpg" for k in imaging.SIZE_PRESETS},
    }


# ---------------- F1 结构化 ----------------

@app.post("/api/products/{pid}/structure")
def structure(pid: int):
    p = db.get_product(pid)
    if not p:
        raise HTTPException(404, "商品不存在")
    t0 = time.time()
    image_b64 = None
    if p.get("image_path") and Path(p["image_path"]).exists():
        vl_img = imaging.compress_for_vl(p["image_path"])  # 大图压缩后送模型
        image_b64 = base64.b64encode(Path(vl_img).read_bytes()).decode()
    pim = generator.structure_product(p["name"], p["category"], p["features"],
                                      p["price"], p["target_market"], image_b64)
    pim.setdefault("attributes", {})["category"] = pim.get("category_en", "General")
    db.update_product(pid, pim=pim, status="structured")
    images = imaging.process_product_image(p["image_path"], pid)
    log.info("商品 #%d 结构化完成 (%.2fs, 图片缓存=%s)", pid, time.time() - t0, images.get("cached"))
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
    t0 = time.time()
    # 重建式生成：清除未发布的旧物料与未成功任务，重复生成不翻倍（published 物料保留）
    with db.get_conn() as conn:
        conn.execute("DELETE FROM listings WHERE product_id=? AND status != 'published'", (pid,))
        conn.execute("DELETE FROM tasks WHERE product_id=? AND status != 'success'", (pid,))
    combos = [(pl, lg) for pl in platforms for lg in languages]
    # 并发生成（mock 模式即时；qwen 实时模式下显著缩短总耗时）
    datas = list(_pool.map(lambda c: generator.generate_listing(p["pim"], c[0], c[1]), combos))
    created = []
    for (platform, lang), data in zip(combos, datas):
        listing = db.create_listing(pid, platform, lang, data["title"], data["bullets"],
                                    data["description"], data.get("seo_meta", ""))
        report = rules_engine.validate(platform, listing, _main_image(p), p["pim"])
        db.update_listing(listing["id"], validation=report)
        created.append(db.get_listing(listing["id"]))
    db.update_product(pid, status="generated")
    log.info("商品 #%d 生成 %d 条 Listing (%.2fs)", pid, len(created), time.time() - t0)
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
    # 重校验时保留历史审计字段（改写留痕不随重建丢失）
    old = l.get("validation") or {}
    if isinstance(old, dict) and old.get("last_autofix"):
        report["last_autofix"] = old["last_autofix"]
    db.update_listing(lid, validation=report)
    return report


@app.post("/api/products/{pid}/validate_all")
def validate_all(pid: int):
    """批量校验：返回该商品全部 Listing 的校验状态汇总（矩阵视图数据源）"""
    p = db.get_product(pid)
    if not p:
        raise HTTPException(404, "商品不存在")
    out = []
    for l in db.list_listings(pid):
        report = rules_engine.validate(l["platform"], l, _main_image(p), p.get("pim"))
        old = l.get("validation") or {}
        if isinstance(old, dict) and old.get("last_autofix"):
            report["last_autofix"] = old["last_autofix"]  # 保留改写留痕
        db.update_listing(l["id"], validation=report)
        out.append({"id": l["id"], "platform": l["platform"], "language": l["language"],
                    "status": l["status"], "passed": report["passed"], "summary": report["summary"]})
    return {"items": out}


@app.post("/api/listings/{lid}/autofix")
def autofix(lid: int):
    l = db.get_listing(lid)
    if not l:
        raise HTTPException(404, "Listing 不存在")
    p = db.get_product(l["product_id"])
    fixed, fix_log = rules_engine.autofix(l["platform"], l, _main_image(p), p.get("pim"))
    db.update_listing(lid, title=fixed["title"], bullets=fixed["bullets"],
                      description=fixed["description"], seo_meta=fixed.get("seo_meta", ""))
    report = rules_engine.validate(l["platform"], db.get_listing(lid),
                                   _main_image(p), p.get("pim"))
    # 修复日志并入校验报告持久化（审计留痕：谁在何时被哪些规则改写过）
    report["last_autofix"] = {**fix_log, "at": datetime.now().isoformat(timespec="seconds")}
    db.update_listing(lid, validation=report)
    log.info("Listing #%d 自动改写 %d 项", lid, len(fix_log["fixed"]))
    return {"listing": db.get_listing(lid), "fix_log": fix_log, "report": report}


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
    t0 = time.time()
    for l in approved:
        task = db.create_task(pid, l["id"], l["platform"], l["language"])
        ok, msg = fake_adapter_publish(p, l)
        db.update_task(task["id"], status="success" if ok else "failed", message=msg)
        if ok:
            db.update_listing(l["id"], status="published")
    db.update_product(pid, status="published")
    log.info("商品 #%d 上架 %d 个平台 (%.2fs)", pid, len(approved), time.time() - t0)
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
    p["images"] = _product_images(p)
    p["counts"] = _product_counts(pid)
    return p


def _product_counts(pid: int) -> dict:
    listings = db.list_listings(pid)
    return {"listings": len(listings),
            "approved": sum(1 for l in listings if l["status"] in ("approved", "published")),
            "tasks": len(db.list_tasks(pid))}


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
    log.exception("请求处理失败: %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


# 静态资源（前端工作台 + 图片）
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
app.mount("/data", StaticFiles(directory=str(ROOT / "data")), name="data")
app.mount("/assets", StaticFiles(directory=str(ROOT / "assets")), name="assets")


@app.get("/")
def index():
    return FileResponse(str(ROOT / "app" / "static" / "index.html"))
