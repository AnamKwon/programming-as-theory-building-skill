import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Tuple, List

DB_PATH = "commerce.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
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
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            idempotency_key TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            FOREIGN KEY (sku) REFERENCES skus(sku)
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
    conn.close()


class Repository:

    @staticmethod
    def create_sku(sku: str, stock: int) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku, stock) VALUES (?, ?)",
            (sku, stock)
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()
        return sku_id

    @staticmethod
    def get_sku_stock(sku: str) -> Optional[int]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    @staticmethod
    def adjust_stock(sku: str, amount: int) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET stock = stock + ? WHERE sku = ? RETURNING stock",
            (amount, sku)
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return row[0] if row else None

    @staticmethod
    def create_reservation(
        sku: str,
        quantity: int,
        idempotency_key: str,
        created_at: datetime
    ) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (sku, quantity, idempotency_key, "PENDING", created_at.isoformat())
        )
        conn.commit()
        res_id = cursor.lastrowid
        conn.close()
        return res_id

    @staticmethod
    def get_reservation(reservation_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, sku, quantity, status, created_at, idempotency_key
               FROM reservations WHERE id = ?""",
            (reservation_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "sku": row[1],
            "quantity": row[2],
            "status": row[3],
            "created_at": row[4],
            "idempotency_key": row[5]
        }

    @staticmethod
    def get_reservation_by_idempotency_key(idempotency_key: str):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, sku, quantity, status, created_at, idempotency_key
               FROM reservations WHERE idempotency_key = ?""",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "sku": row[1],
            "quantity": row[2],
            "status": row[3],
            "created_at": row[4],
            "idempotency_key": row[5]
        }

    @staticmethod
    def update_reservation_status(reservation_id: int, status: str):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def create_order(reservation_id: int, created_at: datetime) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, created_at.isoformat())
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()
        return order_id

    @staticmethod
    def get_orders(page: int = 1, size: int = 10) -> Tuple[List, int]:
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        conn.close()

        orders = [
            {
                "id": row[0],
                "reservation_id": row[1],
                "created_at": row[2]
            }
            for row in rows
        ]
        return orders, total

    @staticmethod
    def sku_exists(sku: str) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM skus WHERE sku = ?", (sku,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
