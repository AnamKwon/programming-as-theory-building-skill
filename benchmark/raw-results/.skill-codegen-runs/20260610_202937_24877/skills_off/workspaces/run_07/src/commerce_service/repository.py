import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
import os


DATABASE_URL = os.getenv("DATABASE_URL", ":memory:")


class Repository:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_url)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
                (sku, initial_stock),
            )
            conn.commit()
            sku_id = cursor.lastrowid
            return {"id": sku_id, "sku": sku, "available_stock": initial_stock}
        except sqlite3.IntegrityError:
            conn.close()
            raise ValueError(f"SKU {sku} already exists")
        finally:
            conn.close()

    def get_sku_by_name(self, sku: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def adjust_stock(self, sku: str, amount: int) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (amount, sku),
        )
        conn.commit()

        cursor.execute(
            "SELECT available_stock FROM skus WHERE sku = ?",
            (sku,),
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            raise ValueError(f"SKU {sku} not found")

        return {"sku": sku, "available_stock": row[0]}

    def create_reservation(
        self, sku_id: int, sku: str, quantity: int, idempotency_key: str
    ) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()

        try:
            cursor.execute(
                """
                INSERT INTO reservations (sku_id, sku, quantity, status, created_at, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sku_id, sku, quantity, "PENDING", now, idempotency_key),
            )
            conn.commit()
            reservation_id = cursor.lastrowid
            return {
                "id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "status": "PENDING",
                "created_at": now,
            }
        finally:
            conn.close()

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def get_reservation_by_id(self, reservation_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def update_reservation_status(self, reservation_id: int, status: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )
        conn.commit()
        conn.close()

    def create_order(self, reservation_id: int) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()

        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, now),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return {
            "id": order_id,
            "reservation_id": reservation_id,
            "created_at": now,
        }

    def get_orders(self, page: int = 1, size: int = 10) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [dict(row) for row in rows]
        return {
            "orders": orders,
            "page": page,
            "size": size,
            "total": total,
        }

    def reserve_stock(self, sku_id: int, quantity: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT available_stock FROM skus WHERE id = ?",
            (sku_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return False

        available_stock = row[0]
        return available_stock >= quantity

    def deduct_stock(self, sku: str, quantity: int):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock - ? WHERE sku = ?",
            (quantity, sku),
        )
        conn.commit()
        conn.close()

    def restore_stock(self, sku: str, quantity: int):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (quantity, sku),
        )
        conn.commit()
        conn.close()
