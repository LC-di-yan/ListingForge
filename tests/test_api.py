"""API 集成测试：六步全流程 + 新增能力（批量校验/上传校验/会话数据）"""
import io


def test_meta(client):
    meta = client.get("/api/meta").json()
    assert meta["mode"] in ("mock", "qwen")
    assert {p["key"] for p in meta["platforms"]} == {"amazon", "aliexpress", "tiktok_shop", "shopify"}


def test_full_flow(client):
    # 1. 录入
    pid = client.post("/api/products/sample/bottle").json()["id"]
    # 2. 结构化
    r = client.post(f"/api/products/{pid}/structure").json()
    assert r["product"]["pim"]["attributes"]["material"] == "Stainless Steel"
    assert r["images"]["main"].startswith(f"/data/uploads/{pid}/images/")
    # 3. 生成 4 平台 × 2 语言
    ls = client.post(f"/api/products/{pid}/generate",
                     data={"platforms": ["amazon", "aliexpress", "tiktok_shop", "shopify"],
                           "languages": ["en", "es"]}).json()["listings"]
    assert len(ls) == 8
    # 4. 校验：亚马逊应全过；速卖通 mock 稿含促销词应违规且可自动改写
    amz = next(l for l in ls if l["platform"] == "amazon" and l["language"] == "en")
    assert client.get(f"/api/listings/{amz['id']}/validate").json()["passed"]
    alx = next(l for l in ls if l["platform"] == "aliexpress" and l["language"] == "en")
    assert not client.get(f"/api/listings/{alx['id']}/validate").json()["passed"]
    fix = client.post(f"/api/listings/{alx['id']}/autofix").json()
    assert fix["report"]["passed"]
    # 批量校验矩阵
    va = client.post(f"/api/products/{pid}/validate_all").json()
    assert len(va["items"]) == 8 and all("passed" in i for i in va["items"])
    # 5. 审核（改稿 + 放行）
    client.put(f"/api/listings/{amz['id']}", data={"title": amz["title"] + " (Edited)"})
    for l in ls:
        if l["language"] == "en":
            client.post(f"/api/listings/{l['id']}/approve")
    detail = client.get(f"/api/products/{pid}").json()
    assert detail["counts"]["approved"] == 4
    # 6. 上架
    tasks = client.post(f"/api/products/{pid}/publish").json()["tasks"]
    assert len(tasks) == 4 and all(t["status"] == "success" for t in tasks)
    assert client.get(f"/api/products/{pid}").json()["status"] == "published"
    # 未放行不可上架（新商品）
    pid2 = client.post("/api/products/sample/earbuds").json()["id"]
    client.post(f"/api/products/{pid2}/structure")
    client.post(f"/api/products/{pid2}/generate", data={"platforms": "amazon", "languages": "en"})
    assert client.post(f"/api/products/{pid2}/publish").status_code == 400


def test_upload_validation(client):
    r = client.post("/api/products", data={"name": "t"},
                    files={"image": ("a.txt", io.BytesIO(b"x"), "text/plain")})
    assert r.status_code == 400  # 非图片拒绝
    png = io.BytesIO(base64_png())
    r = client.post("/api/products", data={"name": "自定义商品", "features": "防漏;便携"},
                    files={"image": ("a.png", png, "image/png")})
    assert r.status_code == 200
    assert r.json()["image_path"]  # 落盘成功


def test_generate_is_idempotent(client):
    """重复生成不翻倍（v1.2 R1 回归）"""
    pid = client.post("/api/products/sample/feeder").json()["id"]
    client.post(f"/api/products/{pid}/structure")
    data = {"platforms": ["amazon", "tiktok_shop"], "languages": ["en"]}
    client.post(f"/api/products/{pid}/generate", data=data)
    client.post(f"/api/products/{pid}/generate", data=data)  # 第二次生成
    listings = client.get(f"/api/products/{pid}/listings").json()
    assert len(listings) == 2  # 而非 4


def test_publish_twice_rejected(client, structured_bottle):
    """已全部上架后重复发布应 400（没有新的已放行物料）"""
    pid = structured_bottle
    data = {"platforms": ["amazon"], "languages": ["en"]}
    ls = client.post(f"/api/products/{pid}/generate", data=data).json()["listings"]
    client.post(f"/api/listings/{ls[0]['id']}/approve")
    assert client.post(f"/api/products/{pid}/publish").status_code == 200
    assert client.post(f"/api/products/{pid}/publish").status_code == 400


def test_upload_filename_traversal_blocked(client, tmp_path):
    """路径穿越文件名被净化（v1.2 R2 安全回归）"""
    r = client.post("/api/products", data={"name": "t"},
                    files={"image": ("../../evil.png", io.BytesIO(base64_png()), "image/png")})
    assert r.status_code == 200
    saved = r.json()["image_path"].replace("\\", "/")
    assert saved.endswith("evil.png") and "/raw/" in saved      # 落在 raw 目录内
    assert "../" not in saved.split("/raw/")[-1]                # 无路径成分
    client.delete(f"/api/products/{r.json()['id']}")


def test_delete_cascades(client):
    """删除商品级联清空物料与任务（v1.3 T5）"""
    pid = client.post("/api/products/sample/earbuds").json()["id"]
    client.post(f"/api/products/{pid}/structure")
    client.post(f"/api/products/{pid}/generate", data={"platforms": "amazon", "languages": "en"})
    assert len(client.get(f"/api/products/{pid}/listings").json()) == 1
    assert client.delete(f"/api/products/{pid}").status_code == 200
    assert client.get(f"/api/products/{pid}").status_code == 404
    assert client.get(f"/api/products/{pid}/listings").json() == []
    assert client.get(f"/api/products/{pid}/tasks").json() == []


def test_autofix_log_persisted(client, structured_bottle):
    """自动改写日志并入校验报告落库（v1.3 T2 审计留痕）"""
    pid = structured_bottle
    data = {"platforms": ["aliexpress"], "languages": ["en"]}
    ls = client.post(f"/api/products/{pid}/generate", data=data).json()["listings"]
    fix = client.post(f"/api/listings/{ls[0]['id']}/autofix").json()
    assert fix["fix_log"]["fixed"]
    # 落库：重新拉取 listing，validation 报告内含 last_autofix
    l = next(x for x in client.get(f"/api/products/{pid}/listings").json() if x["id"] == ls[0]["id"])
    assert l["validation"]["last_autofix"]["fixed"]
    assert l["validation"]["last_autofix"]["at"]
    assert l["validation"]["ruleset_version"] == "v1.3.0"
    # 重新校验后留痕仍在（报告重建不丢审计字段）
    client.get(f"/api/listings/{ls[0]['id']}/validate")
    l2 = next(x for x in client.get(f"/api/products/{pid}/listings").json() if x["id"] == ls[0]["id"])
    assert l2["validation"]["last_autofix"]["fixed"]


def base64_png() -> bytes:
    import base64
    # 1x1 白色 PNG
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def test_session_restore_data(client):
    """前端刷新恢复所需数据齐备：列表 / 详情含 counts 与 images"""
    pid = client.post("/api/products/sample/feeder").json()["id"]
    client.post(f"/api/products/{pid}/structure")
    products = client.get("/api/products").json()
    assert len(products) == 1
    detail = client.get(f"/api/products/{pid}").json()
    assert detail["counts"]["listings"] == 0
    assert detail["images"]["main"].endswith("main_white.jpg")
