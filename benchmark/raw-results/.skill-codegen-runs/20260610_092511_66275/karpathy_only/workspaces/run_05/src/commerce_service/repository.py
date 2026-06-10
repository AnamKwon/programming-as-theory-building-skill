import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import OrderStatus, ReservationStatus


class Database:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._initialize()

    def _initialize(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_code TEXT UNIQUE NOT NULL,
                    stock_qty INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    qty INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus (id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL,
                    sku_id INTEGER NOT NULL,
                    qty INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'created',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations (id),
                    FOREIGN KEY (sku_id) REFERENCES skus (id)
                )
                """
            )
            conn.commit()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_sku(self, sku_code: str, stock_qty: int) -> dict:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO skus (sku_code, stock_qty) VALUES (?, ?)",
                (sku_code, stock_qty),
            )
            conn.commit()
            return self.get_sku_by_id(cursor.lastrowid)

    def get_sku_by_code(self, sku_code: str) -> Optional[dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT id, sku_code, stock_qty FROM skus WHERE sku_code = ?",
                (sku_code,),
            ).fetchone()
            return dict(row) if row else None

    def get_sku_by_id(self, sku_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT id, sku_code, stock_qty FROM skus WHERE id = ?",
                (sku_id,),
            ).fetchone()
            return dict(row) if row else None

    def adjust_stock(self, sku_id: int, adjustment: int) -> dict:
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE skus SET stock_qty = stock_qty + ? WHERE id = ?",
                (adjustment, sku_id),
            )
            conn.commit()
            return self.get_sku_by_id(sku_id)

    def create_reservation(
        self, sku_id: int, qty: int, idempotency_key: str, ttl_minutes: int = 15
    ) -> dict:
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=ttl_minutes)
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reservations
                (sku_id, qty, status, idempotency_key, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sku_id,
                    qty,
                    ReservationStatus.PENDING.value,
                    idempotency_key,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            conn.commit()
            return self.get_reservation_by_id(cursor.lastrowid)

    def get_reservation_by_id(self, reservation_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT r.id, r.sku_id, s.sku_code, r.qty, r.status,
                       r.created_at, r.expires_at
                FROM reservations r
                JOIN skus s ON r.sku_id = s.id
                WHERE r.id = ?
                """,
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT r.id, r.sku_id, s.sku_code, r.qty, r.status,
                       r.created_at, r.expires_at
                FROM reservations r
                JOIN skus s ON r.sku_id = s.id
                WHERE r.idempotency_key = ?
                """,
                (key,),
            ).fetchone()
            return dict(row) if row else None

    def confirm_reservation(self, reservation_id: int) -> dict:
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE reservations SET status = ? WHERE id = ?
                """,
                (ReservationStatus.CONFIRMED.value, reservation_id),
            )
            conn.commit()
            return self.get_reservation_by_id(reservation_id)

    def cancel_reservation(self, reservation_id: int) -> dict:
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE reservations SET status = ? WHERE id = ?
                """,
                (ReservationStatus.CANCELLED.value, reservation_id),
            )
            conn.commit()
            return self.get_reservation_by_id(reservation_id)

    def create_order(self, reservation_id: int, sku_id: int, qty: int) -> dict:
        now = datetime.utcnow()
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO orders (reservation_id, sku_id, qty, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (reservation_id, sku_id, qty, OrderStatus.CREATED.value, now.isoformat()),
            )
            conn.commit()
            return self.get_order_by_id(cursor.lastrowid)

    def get_order_by_id(self, order_id: int) -> Optional[dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT o.id, s.sku_code, o.qty, o.status, o.created_at
                FROM orders o
                JOIN skus s ON o.sku_id = s.id
                WHERE o.id = ?
                """,
                (order_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_orders(self, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        with self.get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            rows = conn.execute(
                """
                SELECT o.id, s.sku_code, o.qty, o.status, o.created_at
                FROM orders o
                JOIN skus s ON o.sku_id = s.id
                ORDER BY o.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            return [dict(row) for row in rows], total
