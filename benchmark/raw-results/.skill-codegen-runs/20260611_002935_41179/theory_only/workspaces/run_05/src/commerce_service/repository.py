import sqlite3
from datetime import datetime
from typing import Optional, Tuple
from pathlib import Path


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
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
                available_stock INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                idempotency_key TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
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
            sku_id = cursor.lastrowid

            cursor.execute("SELECT * FROM skus WHERE id = ?", (sku_id,))
            row = cursor.fetchone()
            return dict(row)
        finally:
            conn.close()

    def get_sku(self, sku: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def adjust_stock(self, sku: str, amount: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "UPDATE skus SET available_stock = available_stock + ?, updated_at = CURRENT_TIMESTAMP WHERE sku = ?",
                (amount, sku)
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO reservations (sku, quantity, idempotency_key, status) VALUES (?, ?, ?, ?)",
                (sku, quantity, idempotency_key, "PENDING")
            )
            conn.commit()
            reservation_id = cursor.lastrowid

            cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
            row = cursor.fetchone()
            return dict(row)
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
            return dict(row) if row else None
        finally:
            conn.close()

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_reservation_status(self, reservation_id: int, status: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "UPDATE reservations SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, reservation_id)
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_order(self, reservation_id: int) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO orders (reservation_id) VALUES (?)",
                (reservation_id,)
            )
            conn.commit()
            order_id = cursor.lastrowid

            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()
            return dict(row)
        finally:
            conn.close()

    def get_orders_paginated(self, page: int = 1, size: int = 10) -> Tuple[list, int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) as count FROM orders")
            total = cursor.fetchone()["count"]

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

    def clear_all(self):
        """Utility for testing - clears all tables"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM reservations")
            cursor.execute("DELETE FROM skus")
            conn.commit()
        finally:
            conn.close()
