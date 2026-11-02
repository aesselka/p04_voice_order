# sqlite: корзины, правила upsell и стоп-лист, переживают перезапуск
# корзина хранится одной json-строкой, читается и пишется целиком
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS carts (
    id         TEXT PRIMARY KEY,
    state      TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS upsell_rules (
    position INTEGER PRIMARY KEY,
    trigger  TEXT NOT NULL,
    offer    TEXT NOT NULL,
    text     TEXT
);
CREATE TABLE IF NOT EXISTS stop_list (
    item_id TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
CART_TTL_S = 24 * 3600          # корзины старше суток удаляем


class Store:
    def __init__(self, path: str | Path):
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()   # эндпоинты вызываются из разных потоков
        with self._lock:
            self._db.executescript(SCHEMA)

    # корзины
    def load_cart(self, cart_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT state FROM carts WHERE id = ?", (cart_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_cart(self, cart_id: str, state: dict) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO carts (id, state, updated_at) VALUES (?, ?, ?)",
                             (cart_id, json.dumps(state, ensure_ascii=False), time.time()))

    def delete_cart(self, cart_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM carts WHERE id = ?", (cart_id,))

    def purge_old_carts(self, ttl_s: float = CART_TTL_S) -> int:
        with self._lock, self._db:
            return self._db.execute("DELETE FROM carts WHERE updated_at < ?", (time.time() - ttl_s,)).rowcount

    def clear(self) -> None:
        # только для тестов
        with self._lock, self._db:
            self._db.execute("DELETE FROM carts")

    # upsell
    def upsell_rules(self) -> Optional[list[dict]]:
        # none - правила еще не сохраняли, берем по умолчанию
        with self._lock:
            rows = self._db.execute("SELECT trigger, offer, text FROM upsell_rules ORDER BY position").fetchall()
            saved = self._db.execute("SELECT 1 FROM settings WHERE key = 'upsell_saved'").fetchone()
        if not rows and not saved:
            return None
        return [{"trigger": t, "offer": o, "text": x} for t, o, x in rows]

    def save_upsell_rules(self, rules: list[dict]) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM upsell_rules")
            self._db.executemany("INSERT INTO upsell_rules (position, trigger, offer, text) VALUES (?, ?, ?, ?)",
                                 [(i, r["trigger"], r["offer"], r.get("text")) for i, r in enumerate(rules)])
            # пустой список тоже запоминаем, иначе вернутся правила по умолчанию
            self._db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('upsell_saved', '1')")

    # стоп-лист
    def stop_list(self) -> list[str]:
        with self._lock:
            rows = self._db.execute("SELECT item_id FROM stop_list ORDER BY item_id").fetchall()
        return [r[0] for r in rows]

    def save_stop_list(self, item_ids: list[str]) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM stop_list")
            self._db.executemany("INSERT OR IGNORE INTO stop_list (item_id) VALUES (?)", [(i,) for i in item_ids])
