"""Data access layer."""

import sqlite3
from datetime import datetime
from typing import Optional

from .models import OrderStatus, ReservationStatus


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                price REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL UNIQUE,
                available_quantity INTEGER NOT NULL DEFAULT 0,
                reserved_quantity INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id INTEGER NOT NULL,
                sku_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
            """
        )

        conn.commit()
        conn.close()

    def create_sku(self, name: str, price: float) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (name, price) VALUES (?, ?)",
            (name, price),
        )
        conn.commit()
        sku_id = cursor.lastrowid

        # Create stock entry
        cursor.execute(
            "INSERT INTO stock (sku_id, available_quantity) VALUES (?, ?)",
            (sku_id, 0),
        )
        conn.commit()
        conn.close()
        return sku_id

    def get_sku(self, sku_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def adjust_stock(self, sku_id: int, quantity: int) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE stock SET available_quantity = available_quantity + ? WHERE sku_id = ?",
            (quantity, sku_id),
        )
        conn.commit()
        conn.close()

    def get_stock(self, sku_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, sku_id, available_quantity, reserved_quantity FROM stock WHERE sku_id = ?",
            (sku_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reservations (sku_id, quantity, idempotency_key, expires_at, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku_id, quantity, idempotency_key, expires_at.isoformat(), ReservationStatus.PENDING),
        )
        conn.commit()
        reservation_id = cursor.lastrowid

        # Update reserved quantity
        cursor.execute(
            "UPDATE stock SET reserved_quantity = reserved_quantity + ? WHERE sku_id = ?",
            (quantity, sku_id),
        )
        conn.commit()
        conn.close()
        return reservation_id

    def get_reservation(self, reservation_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, sku_id, quantity, status, expires_at FROM reservations WHERE id = ?
            """,
            (reservation_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def find_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, sku_id, quantity, status, expires_at FROM reservations
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_reservation_status(self, reservation_id: int, status: str) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )
        conn.commit()
        conn.close()

    def update_reservation_status_and_stock(
        self,
        reservation_id: int,
        status: str,
        sku_id: int,
        quantity: int,
    ) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE id = ?",
            (status, reservation_id),
        )

        if status == ReservationStatus.CONFIRMED:
            # Mark as confirmed: deduct from available
            cursor.execute(
                "UPDATE stock SET available_quantity = available_quantity - ?, reserved_quantity = reserved_quantity - ? WHERE sku_id = ?",
                (quantity, quantity, sku_id),
            )
        elif status == ReservationStatus.CANCELLED:
            # Release reservation
            cursor.execute(
                "UPDATE stock SET reserved_quantity = reserved_quantity - ? WHERE sku_id = ?",
                (quantity, sku_id),
            )

        conn.commit()
        conn.close()

    def create_order(
        self,
        reservation_id: int,
        sku_id: int,
        quantity: int,
        status: str = OrderStatus.PENDING,
    ) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (reservation_id, sku_id, quantity, status)
            VALUES (?, ?, ?, ?)
            """,
            (reservation_id, sku_id, quantity, status),
        )
        conn.commit()
        order_id = cursor.lastrowid
        conn.close()
        return order_id

    def get_order(self, order_id: int) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, reservation_id, sku_id, quantity, status, created_at FROM orders WHERE id = ?",
            (order_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT id, reservation_id, sku_id, quantity, status, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, skip),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows], total

    def update_order_status(self, order_id: int, status: str) -> None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id),
        )
        conn.commit()
        conn.close()
