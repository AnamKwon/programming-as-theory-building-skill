import sqlite3
from datetime import datetime
from typing import Optional, List, Tuple
import os

DATABASE_FILE = "commerce.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            sku TEXT PRIMARY KEY,
            available_stock INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
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


class Repository:
    def __init__(self):
        pass

    def create_sku(self, sku: str, initial_stock: int) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
                (sku, initial_stock)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_sku(self, sku: str) -> Optional[dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def adjust_stock(self, sku: str, amount: int) -> Optional[int]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku)
            )
            if cursor.rowcount == 0:
                conn.close()
                return None
            conn.commit()
            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception:
            conn.close()
            return None

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str, status: str = "PENDING"
    ) -> Optional[dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            created_at = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO reservations (sku, quantity, status, created_at, idempotency_key)
                   VALUES (?, ?, ?, ?, ?)""",
                (sku, quantity, status, created_at, idempotency_key)
            )
            conn.commit()
            reservation_id = cursor.lastrowid
            conn.close()
            return {
                "id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "status": status,
                "created_at": created_at,
                "idempotency_key": idempotency_key
            }
        except sqlite3.IntegrityError:
            conn.close()
            return None

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id)
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def create_order(
        self, reservation_id: int, sku: str, quantity: int
    ) -> Optional[dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            created_at = datetime.utcnow().isoformat()
            cursor.execute(
                """INSERT INTO orders (reservation_id, sku, quantity, created_at)
                   VALUES (?, ?, ?, ?)""",
                (reservation_id, sku, quantity, created_at)
            )
            conn.commit()
            order_id = cursor.lastrowid
            conn.close()
            return {
                "id": order_id,
                "reservation_id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "created_at": created_at
            }
        except Exception:
            conn.close()
            return None

    def get_orders(self, page: int = 1, size: int = 10) -> Tuple[List[dict], int]:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [dict(row) for row in rows]
        return orders, total

    def deduct_stock(self, sku: str, quantity: int) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock - ? WHERE sku = ? AND available_stock >= ?",
            (quantity, sku, quantity)
        )
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def restore_stock(self, sku: str, quantity: int) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
            (quantity, sku)
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
