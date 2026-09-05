"""pytest fixtures：临时 DB / 临时上传目录 / TestClient"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.database as db
    import app.imaging as imaging
    import app.main as main

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(main, "UPLOADS", uploads)
    monkeypatch.setattr(imaging, "UPLOADS", uploads)

    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def structured_bottle(client):
    """已创建并结构化的保温杯商品"""
    pid = client.post("/api/products/sample/bottle").json()["id"]
    client.post(f"/api/products/{pid}/structure")
    return pid
