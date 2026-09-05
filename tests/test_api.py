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
