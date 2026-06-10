import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    sku TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    stock INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY,
                    reservation_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    reservation_id TEXT NOT NULL UNIQUE,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)
            conn.commit()

    def create_sku(self, sku: str, name: str, initial_stock: int) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            created_at = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO skus (sku, name, stock, created_at) VALUES (?, ?, ?, ?)",
                (sku, name, initial_stock, created_at),
            )
            conn.commit()
            return {
                "sku": sku,
                "name": name,
                "stock": initial_stock,
                "created_at": created_at,
            }

    def get_sku(self, sku: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT sku, name, stock, created_at FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            if row:
                return {
                    "sku": row[0],
                    "name": row[1],
                    "stock": row[2],
                    "created_at": row[3],
                }
        return None

    def adjust_stock(self, sku: str, delta: int) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            if not row:
                return None

            new_stock = row[0] + delta
            conn.execute("UPDATE skus SET stock = ? WHERE sku = ?", (new_stock, sku))
            conn.commit()

            return {"sku": sku, "stock": new_stock}

    def create_reservation(self, sku: str, quantity: int, ttl_seconds: int) -> dict:
        res_id = str(uuid.uuid4())
        now = datetime.utcnow()
        created_at = now.isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO reservations (id, sku, quantity, state, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (res_id, sku, quantity, "pending", expires_at, created_at),
            )
            conn.commit()

        return {
            "id": res_id,
            "sku": sku,
            "quantity": quantity,
            "state": "pending",
            "expires_at": expires_at,
            "created_at": created_at,
        }

    def get_reservation(self, res_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, sku, quantity, state, expires_at, created_at FROM reservations WHERE id = ?",
                (res_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "sku": row[1],
                    "quantity": row[2],
                    "state": row[3],
                    "expires_at": row[4],
                    "created_at": row[5],
                }
        return None

    def update_reservation_state(self, res_id: str, state: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE reservations SET state = ? WHERE id = ?", (state, res_id))
            conn.commit()

    def record_idempotency_key(self, key: str, res_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            created_at = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO idempotency_keys (key, reservation_id, created_at) VALUES (?, ?, ?)",
                (key, res_id, created_at),
            )
            conn.commit()

    def get_idempotency_key(self, key: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT key, reservation_id FROM idempotency_keys WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            if row:
                return {"key": row[0], "reservation_id": row[1]}
        return None

    def create_order(self, reservation_id: str, sku: str, quantity: int) -> dict:
        order_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO orders (id, reservation_id, sku, quantity, state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (order_id, reservation_id, sku, quantity, "reserved", now),
            )
            conn.commit()

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "sku": sku,
            "quantity": quantity,
            "state": "reserved",
            "created_at": now,
            "confirmed_at": None,
        }

    def get_order(self, order_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, reservation_id, sku, quantity, state, created_at, confirmed_at FROM orders WHERE id = ?",
                (order_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "reservation_id": row[1],
                    "sku": row[2],
                    "quantity": row[3],
                    "state": row[4],
                    "created_at": row[5],
                    "confirmed_at": row[6],
                }
        return None

    def list_orders(self, offset: int = 0, limit: int = 10) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT id, reservation_id, sku, quantity, state, created_at, confirmed_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()
            items = [
                {
                    "id": row[0],
                    "reservation_id": row[1],
                    "sku": row[2],
                    "quantity": row[3],
                    "state": row[4],
                    "created_at": row[5],
                    "confirmed_at": row[6],
                }
                for row in rows
            ]

        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def confirm_order(self, order_id: str) -> Optional[dict]:
        confirmed_at = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE orders SET state = ?, confirmed_at = ? WHERE id = ?",
                ("confirmed", confirmed_at, order_id),
            )
            conn.commit()

        return self.get_order(order_id)

    def cancel_order(self, order_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE orders SET state = ? WHERE id = ?", ("cancelled", order_id))
            conn.commit()

        return self.get_order(order_id)
