import sqlite3
from datetime import datetime
from typing import Optional


DB_PATH = "commerce.db"


class Repository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
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
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                FOREIGN KEY (sku) REFERENCES skus(sku)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
                (sku, initial_stock)
            )
            conn.commit()
            return {"sku": sku, "available_stock": initial_stock}
        finally:
            conn.close()

    def get_sku(self, sku: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku)
            )
            conn.commit()

            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            if row:
                return {"sku": sku, "available_stock": row[0]}
            return None
        finally:
            conn.close()

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO reservations (sku, quantity, status, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sku, quantity, "PENDING", idempotency_key, now)
            )
            conn.commit()

            cursor.execute("SELECT last_insert_rowid()")
            reservation_id = cursor.fetchone()[0]

            return {
                "id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "status": "PENDING",
                "idempotency_key": idempotency_key,
                "created_at": now
            }
        finally:
            conn.close()

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def create_order(self, reservation_id: int, sku: str, quantity: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO orders (reservation_id, sku, quantity, created_at)
                   VALUES (?, ?, ?, ?)""",
                (reservation_id, sku, quantity, now)
            )
            conn.commit()

            cursor.execute("SELECT last_insert_rowid()")
            order_id = cursor.fetchone()[0]

            return {
                "id": order_id,
                "reservation_id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "created_at": now
            }
        finally:
            conn.close()

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            offset = (page - 1) * size
            cursor.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (size, offset)
            )
            rows = cursor.fetchall()
            orders = [dict(row) for row in rows]

            return orders, total
        finally:
            conn.close()
