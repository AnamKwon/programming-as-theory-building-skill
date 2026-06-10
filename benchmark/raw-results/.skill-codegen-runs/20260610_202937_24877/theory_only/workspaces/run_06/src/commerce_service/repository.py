"""Data access layer for database operations."""

import sqlite3
from datetime import datetime
from pathlib import Path


DATABASE_FILE = "commerce.db"


class Repository:
    def __init__(self, db_file: str = DATABASE_FILE):
        self.db_file = db_file
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_connection()
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
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus (sku)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations (id)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> dict:
        conn = self.get_connection()
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

    def get_sku(self, sku: str) -> dict | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT sku, available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def adjust_stock(self, sku: str, amount: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (amount, sku)
            )
            conn.commit()

            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            available_stock = row["available_stock"] if row else 0
            return {"sku": sku, "available_stock": available_stock}
        finally:
            conn.close()

    def get_available_stock(self, sku: str) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT available_stock FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return row["available_stock"] if row else 0
        finally:
            conn.close()

    def check_idempotency_key(self, idempotency_key: str) -> dict | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, sku, quantity, status, created_at FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str, created_at: str
    ) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO reservations (sku, quantity, idempotency_key, status, created_at)
                VALUES (?, ?, ?, 'PENDING', ?)
                """,
                (sku, quantity, idempotency_key, created_at)
            )
            conn.commit()

            reservation_id = cursor.lastrowid
            return {
                "id": reservation_id,
                "sku": sku,
                "quantity": quantity,
                "status": "PENDING",
                "created_at": created_at
            }
        finally:
            conn.close()

    def deduct_stock(self, sku: str, quantity: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock - ? WHERE sku = ?",
                (quantity, sku)
            )
            conn.commit()
        finally:
            conn.close()

    def restore_stock(self, sku: str, quantity: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ? WHERE sku = ?",
                (quantity, sku)
            )
            conn.commit()
        finally:
            conn.close()

    def get_reservation(self, reservation_id: int) -> dict | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, sku, quantity, status, created_at FROM reservations WHERE id = ?",
                (reservation_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_reservation_status(self, reservation_id: int, status: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status, reservation_id)
            )
            conn.commit()
        finally:
            conn.close()

    def create_order(self, reservation_id: int, created_at: str) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
                (reservation_id, created_at)
            )
            conn.commit()

            order_id = cursor.lastrowid
            return {
                "id": order_id,
                "reservation_id": reservation_id,
                "created_at": created_at
            }
        finally:
            conn.close()

    def get_orders(self, page: int = 1, size: int = 10) -> tuple[list[dict], int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) as total FROM orders")
            total = cursor.fetchone()["total"]

            offset = (page - 1) * size
            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                (size, offset)
            )
            rows = cursor.fetchall()
            orders = [dict(row) for row in rows]
            return orders, total
        finally:
            conn.close()

    def get_order_by_id(self, order_id: int) -> dict | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, reservation_id, created_at FROM orders WHERE id = ?",
                (order_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
