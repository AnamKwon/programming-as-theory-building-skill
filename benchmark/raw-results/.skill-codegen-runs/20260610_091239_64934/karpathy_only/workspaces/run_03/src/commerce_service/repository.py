import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import OrderStatus, ReservationStatus

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._connection = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._connection is None:
                self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
                self._connection.row_factory = sqlite3.Row
            return self._connection
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                sku_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                total_stock INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                confirmed_at TEXT,
                cancelled_at TEXT,
                FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
                UNIQUE(idempotency_key)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_reservations (
                order_id TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                PRIMARY KEY (order_id, reservation_id),
                FOREIGN KEY (order_id) REFERENCES orders(order_id),
                FOREIGN KEY (reservation_id) REFERENCES reservations(reservation_id)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku_id: str, name: str, total_stock: int) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skus (sku_id, name, total_stock, created_at) VALUES (?, ?, ?, ?)",
            (sku_id, name, total_stock, utc_now().isoformat()),
        )
        conn.commit()
        conn.close()

    def get_sku(self, sku_id: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def adjust_stock(self, sku_id: str, quantity_change: int) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE skus SET total_stock = total_stock + ? WHERE sku_id = ?",
            (quantity_change, sku_id),
        )
        conn.commit()
        conn.close()

    def get_reserved_stock(self, sku_id: str) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) as reserved
            FROM reservations
            WHERE sku_id = ? AND status IN (?, ?)
            """,
            (sku_id, ReservationStatus.PENDING.value, ReservationStatus.CONFIRMED.value),
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reservations
            (reservation_id, sku_id, quantity, status, idempotency_key, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reservation_id,
                sku_id,
                quantity,
                ReservationStatus.PENDING.value,
                idempotency_key,
                utc_now().isoformat(),
                expires_at.isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    def get_reservation(self, reservation_id: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (reservation_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?", (idempotency_key,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def confirm_reservation(self, reservation_id: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reservations
            SET status = ?, confirmed_at = ?
            WHERE reservation_id = ?
            """,
            (ReservationStatus.CONFIRMED.value, utc_now().isoformat(), reservation_id),
        )
        conn.commit()
        conn.close()

    def cancel_reservation(self, reservation_id: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reservations
            SET status = ?, cancelled_at = ?
            WHERE reservation_id = ?
            """,
            (ReservationStatus.CANCELLED.value, utc_now().isoformat(), reservation_id),
        )
        conn.commit()
        conn.close()

    def expire_reservations(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reservations
            SET status = ?
            WHERE status = ? AND expires_at < ?
            """,
            (
                ReservationStatus.EXPIRED.value,
                ReservationStatus.PENDING.value,
                utc_now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    def create_order(self, order_id: str, reservation_ids: list[str]) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (order_id, status, created_at) VALUES (?, ?, ?)",
            (order_id, OrderStatus.OPEN.value, utc_now().isoformat()),
        )
        for res_id in reservation_ids:
            cursor.execute(
                "INSERT INTO order_reservations (order_id, reservation_id) VALUES (?, ?)",
                (order_id, res_id),
            )
        conn.commit()
        conn.close()

    def get_order(self, order_id: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_order_reservations(self, order_id: str) -> list[str]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT reservation_id FROM order_reservations WHERE order_id = ?", (order_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]

    def list_orders(self, offset: int = 0, limit: int = 10) -> tuple[list[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        cursor.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        return ([dict(row) for row in rows], total)

    def confirm_order(self, order_id: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET status = ? WHERE order_id = ?",
            (OrderStatus.CONFIRMED.value, order_id),
        )
        conn.commit()
        conn.close()

    def cancel_order(self, order_id: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET status = ? WHERE order_id = ?",
            (OrderStatus.CANCELLED.value, order_id),
        )
        conn.commit()
        conn.close()
