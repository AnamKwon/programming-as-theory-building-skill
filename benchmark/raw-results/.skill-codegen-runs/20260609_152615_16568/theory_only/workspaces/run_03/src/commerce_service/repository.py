"""Repository layer for database access."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from commerce_service.models import OrderStatus, ReservationStatus


class Repository:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_levels (
                sku_id TEXT PRIMARY KEY,
                available INTEGER NOT NULL DEFAULT 0,
                reserved INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reservations_order_id
            ON reservations(order_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reservations_idempotency
            ON reservations(idempotency_key)
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku_id: str, name: str) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO skus (id, name, created_at) VALUES (?, ?, ?)",
                (sku_id, name, datetime.utcnow().isoformat()),
            )
            cursor.execute(
                "INSERT INTO stock_levels (sku_id, available, reserved) VALUES (?, ?, ?)",
                (sku_id, 0, 0),
            )
            conn.commit()
        finally:
            conn.close()

    def get_sku(self, sku_id: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, name FROM skus WHERE id = ?", (sku_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def adjust_stock(self, sku_id: str, adjustment: int) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE stock_levels SET available = available + ? WHERE sku_id = ?",
                (adjustment, sku_id),
            )
            cursor.execute(
                "SELECT available FROM stock_levels WHERE sku_id = ?", (sku_id,)
            )
            row = cursor.fetchone()
            new_level = row[0] if row else 0
            conn.commit()
            return new_level
        finally:
            conn.close()

    def get_stock_level(self, sku_id: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT sku_id, available, reserved FROM stock_levels WHERE sku_id = ?",
                (sku_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def check_idempotency(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, status FROM reservations WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_reservation(
        self,
        reservation_id: str,
        order_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expiration_minutes: int = 15,
    ) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            expires_at = datetime.utcnow() + timedelta(minutes=expiration_minutes)
            cursor.execute(
                """
                INSERT INTO reservations
                (id, order_id, sku_id, quantity, idempotency_key, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation_id,
                    order_id,
                    sku_id,
                    quantity,
                    idempotency_key,
                    ReservationStatus.PENDING.value,
                    datetime.utcnow().isoformat(),
                    expires_at.isoformat(),
                ),
            )
            cursor.execute(
                "UPDATE stock_levels SET reserved = reserved + ? WHERE sku_id = ?",
                (quantity, sku_id),
            )
            if not self._order_exists(cursor, order_id):
                cursor.execute(
                    "INSERT INTO orders (id, status, created_at) VALUES (?, ?, ?)",
                    (order_id, OrderStatus.DRAFT.value, datetime.utcnow().isoformat()),
                )
            conn.commit()
        finally:
            conn.close()

    def get_reservation(self, reservation_id: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, order_id, sku_id, quantity, status, created_at, expires_at
                FROM reservations WHERE id = ?
                """,
                (reservation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def confirm_reservation(self, reservation_id: str) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (ReservationStatus.CONFIRMED.value, reservation_id),
            )
            conn.commit()
        finally:
            conn.close()

    def cancel_reservation(self, reservation_id: str) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT sku_id, quantity FROM reservations WHERE id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()
            if row:
                sku_id, quantity = row[0], row[1]
                cursor.execute(
                    "UPDATE stock_levels SET reserved = reserved - ? WHERE sku_id = ?",
                    (quantity, sku_id),
                )
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (ReservationStatus.CANCELLED.value, reservation_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_order(self, order_id: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, status, created_at FROM orders WHERE id = ?", (order_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_order_reservations(self, order_id: str) -> list[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, order_id, sku_id, quantity, status, created_at, expires_at
                FROM reservations WHERE order_id = ?
                """,
                (order_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def list_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[dict], int]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id, status, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            orders = [dict(row) for row in cursor.fetchall()]
            return orders, total
        finally:
            conn.close()

    def _order_exists(self, cursor: sqlite3.Cursor, order_id: str) -> bool:
        cursor.execute("SELECT 1 FROM orders WHERE id = ?", (order_id,))
        return cursor.fetchone() is not None

    def expire_reservations(self) -> int:
        """Mark expired reservations and release reserved stock."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                SELECT id, sku_id, quantity FROM reservations
                WHERE status = ? AND expires_at < ?
                """,
                (ReservationStatus.PENDING.value, now),
            )
            expired = cursor.fetchall()
            for reservation_id, sku_id, quantity in expired:
                cursor.execute(
                    "UPDATE reservations SET status = ? WHERE id = ?",
                    (ReservationStatus.EXPIRED.value, reservation_id),
                )
                cursor.execute(
                    "UPDATE stock_levels SET reserved = reserved - ? WHERE sku_id = ?",
                    (quantity, sku_id),
                )
            conn.commit()
            return len(expired)
        finally:
            conn.close()
