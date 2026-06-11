"""Database repository layer."""

import sqlite3
from datetime import datetime
from typing import Optional, Tuple
from contextlib import contextmanager


class Database:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    stock INTEGER NOT NULL DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
                )
            """)
            conn.commit()


class Repository:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO skus (sku, stock) VALUES (?, ?)",
                (sku, initial_stock)
            )
            conn.commit()
            sku_id = cursor.lastrowid
            return {
                "id": sku_id,
                "sku": sku,
                "stock": initial_stock
            }

    def get_sku_by_name(self, sku: str) -> Optional[dict]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, sku, stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_sku_by_id(self, sku_id: int) -> Optional[dict]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, sku, stock FROM skus WHERE id = ?", (sku_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def adjust_stock(self, sku: str, amount: int) -> dict:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"SKU {sku} not found")
            sku_id, current_stock = row["id"], row["stock"]
            new_stock = current_stock + amount
            cursor.execute("UPDATE skus SET stock = ? WHERE id = ?", (new_stock, sku_id))
            conn.commit()
            return {"sku": sku, "stock": new_stock}

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.id, s.sku, r.quantity, r.status, r.idempotency_key, r.created_at
                   FROM reservations r
                   JOIN skus s ON r.sku_id = s.id
                   WHERE r.idempotency_key = ?""",
                (key,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def create_reservation(
        self,
        sku_id: int,
        sku: str,
        quantity: int,
        idempotency_key: str,
        created_at: datetime
    ) -> dict:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            created_at_str = created_at.isoformat()
            cursor.execute(
                """INSERT INTO reservations (sku_id, quantity, status, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sku_id, quantity, "PENDING", idempotency_key, created_at_str)
            )
            conn.commit()
            reservation_id = cursor.lastrowid
            return {
                "id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "status": "PENDING",
                "idempotency_key": idempotency_key,
                "created_at": created_at
            }

    def get_reservation_by_id(self, reservation_id: int) -> Optional[dict]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.id, s.sku, r.quantity, r.status, r.idempotency_key, r.created_at
                   FROM reservations r
                   JOIN skus s ON r.sku_id = s.id
                   WHERE r.id = ?""",
                (reservation_id,)
            )
            row = cursor.fetchone()
            if row:
                data = dict(row)
                data["created_at"] = datetime.fromisoformat(data["created_at"])
                return data
            return None

    def update_reservation_status(self, reservation_id: int, status: str) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id)
            )
            conn.commit()

    def create_order(self, reservation_id: int, created_at: datetime) -> dict:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            created_at_str = created_at.isoformat()
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, created_at_str)
            )
            conn.commit()
            order_id = cursor.lastrowid
            return {
                "id": order_id,
                "reservation_id": reservation_id,
                "created_at": created_at
            }

    def list_orders(self, page: int = 1, size: int = 10) -> Tuple[list, int]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM orders")
            total = cursor.fetchone()["count"]
            offset = (page - 1) * size
            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (size, offset)
            )
            rows = cursor.fetchall()
            orders = []
            for row in rows:
                data = dict(row)
                data["created_at"] = datetime.fromisoformat(data["created_at"])
                orders.append(data)
            return orders, total
