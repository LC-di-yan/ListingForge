"""SQLite 持久化层：商品 / Listing / 上架任务。Demo 用 SQLite，生产可平替 PostgreSQL。"""
import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "listingforge.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock, get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT DEFAULT '',
                features TEXT DEFAULT '[]',
                price REAL DEFAULT 0,
                target_market TEXT DEFAULT '',
                image_path TEXT DEFAULT '',
                pim TEXT DEFAULT '',
                status TEXT DEFAULT 'created',
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                language TEXT NOT NULL,
                title TEXT DEFAULT '',
                bullets TEXT DEFAULT '[]',
                description TEXT DEFAULT '',
                seo_meta TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                validation TEXT DEFAULT '',
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                listing_id INTEGER,
                platform TEXT NOT NULL,
                language TEXT DEFAULT '',
                status TEXT DEFAULT 'queued',
                message TEXT DEFAULT '',
                created_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_listings_product ON listings(product_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_product ON tasks(product_id);
            PRAGMA journal_mode=WAL;
            """
        )


def _row_to_product(row) -> dict:
    d = dict(row)
    d["features"] = json.loads(d.get("features") or "[]")
    d["pim"] = json.loads(d["pim"]) if d.get("pim") else None
    return d


def _row_to_listing(row) -> dict:
    d = dict(row)
    d["bullets"] = json.loads(d.get("bullets") or "[]")
    d["validation"] = json.loads(d["validation"]) if d.get("validation") else None
    return d


# ---------------- products ----------------

def create_product(name: str, category: str, features: list, price: float,
                   target_market: str, image_path: str = "") -> dict:
    now = time.time()
    with _lock, get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO products(name, category, features, price, target_market, image_path, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (name, category, json.dumps(features, ensure_ascii=False), price, target_market, image_path, now),
        )
        pid = cur.lastrowid
    return get_product(pid)


def get_product(pid: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    return _row_to_product(row) if row else None


def list_products() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return [_row_to_product(r) for r in rows]


def update_product(pid: int, **fields) -> dict | None:
    allowed = {"name", "category", "features", "price", "target_market", "image_path", "pim", "status"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("features", "pim") and v is not None and not isinstance(v, str):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return get_product(pid)
    vals.append(pid)
    with _lock, get_conn() as conn:
        conn.execute(f"UPDATE products SET {', '.join(sets)} WHERE id=?", vals)
    return get_product(pid)


# ---------------- listings ----------------

def create_listing(product_id: int, platform: str, language: str, title: str,
                   bullets: list, description: str, seo_meta: str = "") -> dict:
    now = time.time()
    with _lock, get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO listings(product_id, platform, language, title, bullets, description, seo_meta, status, updated_at)"
            " VALUES(?,?,?,?,?,?,?, 'draft', ?)",
            (product_id, platform, language, title, json.dumps(bullets, ensure_ascii=False),
             description, seo_meta, now),
        )
        lid = cur.lastrowid
    return get_listing(lid)


def get_listing(lid: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
    return _row_to_listing(row) if row else None


def list_listings(product_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM listings WHERE product_id=? ORDER BY platform, language", (product_id,)
        ).fetchall()
    return [_row_to_listing(r) for r in rows]


def update_listing(lid: int, **fields) -> dict | None:
    allowed = {"title", "bullets", "description", "seo_meta", "status", "validation"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("bullets", "validation") and v is not None and not isinstance(v, str):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k}=?")
        vals.append(v)
    if sets:
        sets.append("updated_at=?")
        vals.append(time.time())
        vals.append(lid)
        with _lock, get_conn() as conn:
            conn.execute(f"UPDATE listings SET {', '.join(sets)} WHERE id=?", vals)
    return get_listing(lid)


def approved_listings_of_product(pid: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM listings WHERE product_id=? AND status='approved'", (pid,)
        ).fetchall()
    return [_row_to_listing(r) for r in rows]


# ---------------- tasks ----------------

def create_task(product_id: int, listing_id: int, platform: str, language: str) -> dict:
    with _lock, get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tasks(product_id, listing_id, platform, language, status, message, created_at)"
            " VALUES(?,?,?,?, 'queued', '', ?)",
            (product_id, listing_id, platform, language, time.time()),
        )
        tid = cur.lastrowid
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    return dict(row)


def update_task(tid: int, **fields):
    allowed = {"status", "message"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if sets:
        vals.append(tid)
        with _lock, get_conn() as conn:
            conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", vals)


def list_tasks(product_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE product_id=? ORDER BY id", (product_id,)
        ).fetchall()
    return [dict(r) for r in rows]
