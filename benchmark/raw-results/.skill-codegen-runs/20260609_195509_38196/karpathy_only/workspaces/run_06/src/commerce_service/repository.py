import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import ReservationStatus


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    sku TEXT PRIMARY KEY,
                    stock INTEGER NOT NULL,
                    reserved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)

            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_reservation_idempotency
                ON reservations(idempotency_key)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    reservation_id TEXT NOT NULL UNIQUE,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    customer_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)

            conn.commit()
            conn.close()

    def create_sku(self, sku: str, stock: int) -> dict:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()

            try:
                cursor.execute(
                    "INSERT INTO skus (sku, stock, reserved, created_at) VALUES (?, ?, ?, ?)",
                    (sku, stock, 0, now),
                )
                conn.commit()
                return self.get_sku(sku)
            finally:
                conn.close()

    def get_sku(self, sku: str) -> Optional[dict]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT sku, stock, reserved, created_at FROM skus WHERE sku = ?", (sku,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {
                "sku": row["sku"],
                "stock": row["stock"],
                "reserved": row["reserved"],
                "created_at": row["created_at"],
            }

    def adjust_stock(self, sku: str, adjustment: int) -> dict:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE skus SET stock = stock + ? WHERE sku = ?",
                (adjustment, sku),
            )
            conn.commit()

            result = self.get_sku(sku)
            conn.close()
            return result

    def create_reservation(
        self,
        reservation_id: str,
        sku: str,
        quantity: int,
        customer_id: str,
        idempotency_key: str,
        expires_at: datetime,
    ) -> dict:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            expires_at_str = expires_at.isoformat()

            try:
                cursor.execute(
                    """
                    INSERT INTO reservations
                    (id, sku, quantity, status, customer_id, idempotency_key, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reservation_id,
                        sku,
                        quantity,
                        ReservationStatus.PENDING.value,
                        customer_id,
                        idempotency_key,
                        now,
                        expires_at_str,
                    ),
                )

                cursor.execute(
                    "UPDATE skus SET reserved = reserved + ? WHERE sku = ?",
                    (quantity, sku),
                )

                conn.commit()
                return self.get_reservation(reservation_id)
            finally:
                conn.close()

    def get_reservation(self, reservation_id: str) -> Optional[dict]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, sku, quantity, status, customer_id, idempotency_key, created_at, expires_at
                FROM reservations WHERE id = ?
                """,
                (reservation_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {
                "id": row["id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "status": row["status"],
                "customer_id": row["customer_id"],
                "idempotency_key": row["idempotency_key"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[dict]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, sku, quantity, status, customer_id, idempotency_key, created_at, expires_at
                FROM reservations WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {
                "id": row["id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "status": row["status"],
                "customer_id": row["customer_id"],
                "idempotency_key": row["idempotency_key"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }

    def update_reservation_status(self, reservation_id: str, status: ReservationStatus) -> dict:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status.value, reservation_id),
            )
            conn.commit()

            result = self.get_reservation(reservation_id)
            conn.close()
            return result

    def release_reservation_stock(self, reservation_id: str):
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT sku, quantity FROM reservations WHERE id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()

            if row:
                cursor.execute(
                    "UPDATE skus SET reserved = reserved - ? WHERE sku = ?",
                    (row["quantity"], row["sku"]),
                )

            conn.commit()
            conn.close()

    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku: str,
        quantity: int,
        customer_id: str,
    ) -> dict:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()

            cursor.execute(
                """
                INSERT INTO orders
                (id, reservation_id, sku, quantity, customer_id, created_at, confirmed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (order_id, reservation_id, sku, quantity, customer_id, now, now),
            )
            conn.commit()

            result = self.get_order(order_id)
            conn.close()
            return result

    def get_order(self, order_id: str) -> Optional[dict]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, reservation_id, sku, quantity, customer_id, created_at, confirmed_at
                FROM orders WHERE id = ?
                """,
                (order_id,),
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {
                "id": row["id"],
                "reservation_id": row["reservation_id"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "customer_id": row["customer_id"],
                "created_at": row["created_at"],
                "confirmed_at": row["confirmed_at"],
            }

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[dict], int]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as total FROM orders")
            total = cursor.fetchone()["total"]

            offset = (page - 1) * page_size
            cursor.execute(
                """
                SELECT id, reservation_id, sku, quantity, customer_id, created_at, confirmed_at
                FROM orders
                ORDER BY confirmed_at DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            )
            rows = cursor.fetchall()
            conn.close()

            orders = [
                {
                    "id": row["id"],
                    "reservation_id": row["reservation_id"],
                    "sku": row["sku"],
                    "quantity": row["quantity"],
                    "customer_id": row["customer_id"],
                    "created_at": row["created_at"],
                    "confirmed_at": row["confirmed_at"],
                }
                for row in rows
            ]

            return orders, total
