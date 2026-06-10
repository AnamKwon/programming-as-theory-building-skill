import sqlite3
from datetime import datetime
from typing import Optional, Tuple, List


DATABASE_PATH = "commerce.db"


def _get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_connection()
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
    conn.close()


class SKURepository:
    @staticmethod
    def create_sku(sku: str, initial_stock: int) -> int:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku, available_stock) VALUES (?, ?)",
            (sku, initial_stock)
        )
        conn.commit()
        sku_id = cursor.lastrowid
        conn.close()
        return sku_id

    @staticmethod
    def get_sku_by_name(sku: str) -> Optional[dict]:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_sku_by_id(sku_id: int) -> Optional[dict]:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, sku, available_stock FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update_stock(sku_id: int, new_stock: int) -> None:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE skus SET available_stock = ? WHERE id = ?", (new_stock, sku_id))
        conn.commit()
        conn.close()


class ReservationRepository:
    @staticmethod
    def create_reservation(sku_id: int, sku: str, quantity: int, idempotency_key: str, created_at: str) -> int:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO reservations (sku_id, sku, quantity, status, idempotency_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sku_id, sku, quantity, "PENDING", idempotency_key, created_at)
        )
        conn.commit()
        reservation_id = cursor.lastrowid
        conn.close()
        return reservation_id

    @staticmethod
    def get_reservation_by_idempotency_key(idempotency_key: str) -> Optional[dict]:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku_id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_reservation_by_id(reservation_id: int) -> Optional[dict]:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku_id, sku, quantity, status, idempotency_key, created_at FROM reservations WHERE id = ?",
            (reservation_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update_reservation_status(reservation_id: int, status: str) -> None:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE reservations SET status = ? WHERE id = ?", (status, reservation_id))
        conn.commit()
        conn.close()


class OrderRepository:
    @staticmethod
    def create_order(reservation_id: int, created_at: str) -> int:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, created_at)
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()
        return order_id

    @staticmethod
    def get_orders(page: int, size: int) -> Tuple[List[dict], int]:
        conn = _get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        offset = (page - 1) * size
        cursor.execute(
            "SELECT id, reservation_id, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
            (size, offset)
        )
        rows = cursor.fetchall()
        conn.close()

        orders = [dict(row) for row in rows]
        return orders, total
