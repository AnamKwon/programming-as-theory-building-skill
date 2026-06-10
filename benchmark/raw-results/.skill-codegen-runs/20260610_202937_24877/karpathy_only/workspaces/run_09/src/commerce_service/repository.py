import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class Database:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None

    def connect(self):
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def disconnect(self):
        if self.connection:
            self.connection.close()

    def _init_schema(self):
        if not self.connection:
            return

        cursor = self.connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                available_stock INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
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

        self.connection.commit()

    def execute_query(self, query: str, params: tuple = ()):
        if not self.connection:
            raise RuntimeError("Database not connected")
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        return cursor

    def execute_insert(self, query: str, params: tuple = ()):
        cursor = self.execute_query(query, params)
        self.connection.commit()
        return cursor.lastrowid

    def execute_update(self, query: str, params: tuple = ()):
        cursor = self.execute_query(query, params)
        self.connection.commit()
        return cursor.rowcount

    def fetch_one(self, query: str, params: tuple = ()):
        cursor = self.execute_query(query, params)
        return cursor.fetchone()

    def fetch_all(self, query: str, params: tuple = ()):
        cursor = self.execute_query(query, params)
        return cursor.fetchall()


class Repository:
    def __init__(self, db: Database):
        self.db = db

    def create_sku(self, sku: str, initial_stock: int) -> int:
        now = datetime.utcnow().isoformat()
        sku_id = self.db.execute_insert(
            "INSERT INTO skus (sku, available_stock, created_at) VALUES (?, ?, ?)",
            (sku, initial_stock, now),
        )
        return sku_id

    def get_sku_by_name(self, sku: str) -> Optional[dict]:
        row = self.db.fetch_one("SELECT * FROM skus WHERE sku = ?", (sku,))
        return dict(row) if row else None

    def get_sku_by_id(self, sku_id: int) -> Optional[dict]:
        row = self.db.fetch_one("SELECT * FROM skus WHERE id = ?", (sku_id,))
        return dict(row) if row else None

    def update_sku_stock(self, sku_id: int, new_stock: int) -> bool:
        count = self.db.execute_update(
            "UPDATE skus SET available_stock = ? WHERE id = ?",
            (new_stock, sku_id),
        )
        return count > 0

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
    ) -> int:
        now = datetime.utcnow().isoformat()
        reservation_id = self.db.execute_insert(
            """
            INSERT INTO reservations (sku_id, quantity, status, idempotency_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sku_id, quantity, "PENDING", idempotency_key, now, now),
        )
        return reservation_id

    def get_reservation_by_id(self, reservation_id: int) -> Optional[dict]:
        row = self.db.fetch_one(
            """
            SELECT r.*, s.sku FROM reservations r
            JOIN skus s ON r.sku_id = s.id
            WHERE r.id = ?
            """,
            (reservation_id,),
        )
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        row = self.db.fetch_one(
            """
            SELECT r.*, s.sku FROM reservations r
            JOIN skus s ON r.sku_id = s.id
            WHERE r.idempotency_key = ?
            """,
            (idempotency_key,),
        )
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        now = datetime.utcnow().isoformat()
        count = self.db.execute_update(
            "UPDATE reservations SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, reservation_id),
        )
        return count > 0

    def create_order(self, reservation_id: int) -> int:
        now = datetime.utcnow().isoformat()
        order_id = self.db.execute_insert(
            "INSERT INTO orders (reservation_id, created_at) VALUES (?, ?)",
            (reservation_id, now),
        )
        return order_id

    def get_orders_paginated(self, page: int, size: int) -> tuple[list[dict], int]:
        offset = (page - 1) * size
        rows = self.db.fetch_all(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        total_row = self.db.fetch_one("SELECT COUNT(*) as count FROM orders")
        total = total_row["count"] if total_row else 0
        return [dict(row) for row in rows], total

    def get_order_by_id(self, order_id: int) -> Optional[dict]:
        row = self.db.fetch_one("SELECT * FROM orders WHERE id = ?", (order_id,))
        return dict(row) if row else None
