import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

from .models import OrderStatus, ReservationStatus


class Database:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._lock = Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skus (
                    sku_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    stock_quantity INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    sku_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    sku_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
                )
                """
            )
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # SKU operations
    def create_sku(self, sku_id: str, name: str, stock_quantity: int) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO skus (sku_id, name, stock_quantity) VALUES (?, ?, ?)",
                    (sku_id, name, stock_quantity),
                )
                conn.commit()
                return {"sku_id": sku_id, "name": name, "stock_quantity": stock_quantity}
            finally:
                conn.close()

    def get_sku(self, sku_id: str) -> dict | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT sku_id, name, stock_quantity FROM skus WHERE sku_id = ?",
                (sku_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE skus SET stock_quantity = stock_quantity + ? WHERE sku_id = ?",
                    (quantity_delta, sku_id),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT sku_id, name, stock_quantity FROM skus WHERE sku_id = ?",
                    (sku_id,),
                ).fetchone()
                return dict(row)
            finally:
                conn.close()

    # Reservation operations
    def create_reservation(
        self,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        expires_in_seconds: int = 3600,
    ) -> dict:
        reservation_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=expires_in_seconds)

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
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
                        now.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
                conn.commit()
                return {
                    "reservation_id": reservation_id,
                    "sku_id": sku_id,
                    "quantity": quantity,
                    "status": ReservationStatus.PENDING.value,
                    "created_at": now,
                    "expires_at": expires_at,
                }
            finally:
                conn.close()

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT reservation_id, sku_id, quantity, status, created_at, expires_at
                FROM reservations WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
            if row:
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"])
                d["expires_at"] = datetime.fromisoformat(d["expires_at"])
                return d
            return None
        finally:
            conn.close()

    def get_reservation(self, reservation_id: str) -> dict | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT reservation_id, sku_id, quantity, status, created_at, expires_at
                FROM reservations WHERE reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
            if row:
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"])
                d["expires_at"] = datetime.fromisoformat(d["expires_at"])
                return d
            return None
        finally:
            conn.close()

    def confirm_reservation(self, reservation_id: str) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE reservations SET status = ? WHERE reservation_id = ?",
                    (ReservationStatus.CONFIRMED.value, reservation_id),
                )
                conn.commit()
                row = conn.execute(
                    """
                    SELECT reservation_id, sku_id, quantity, status, created_at, expires_at
                    FROM reservations WHERE reservation_id = ?
                    """,
                    (reservation_id,),
                ).fetchone()
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"])
                d["expires_at"] = datetime.fromisoformat(d["expires_at"])
                return d
            finally:
                conn.close()

    def cancel_reservation(self, reservation_id: str) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE reservations SET status = ? WHERE reservation_id = ?",
                    (ReservationStatus.CANCELLED.value, reservation_id),
                )
                conn.commit()
                row = conn.execute(
                    """
                    SELECT reservation_id, sku_id, quantity, status, created_at, expires_at
                    FROM reservations WHERE reservation_id = ?
                    """,
                    (reservation_id,),
                ).fetchone()
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"])
                d["expires_at"] = datetime.fromisoformat(d["expires_at"])
                return d
            finally:
                conn.close()

    # Order operations
    def create_order(self, sku_id: str, quantity: int) -> dict:
        order_id = str(uuid.uuid4())
        now = datetime.utcnow()

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO orders (order_id, sku_id, quantity, status, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (order_id, sku_id, quantity, OrderStatus.PENDING.value, now.isoformat()),
                )
                conn.commit()
                return {
                    "order_id": order_id,
                    "sku_id": sku_id,
                    "quantity": quantity,
                    "status": OrderStatus.PENDING.value,
                    "created_at": now,
                }
            finally:
                conn.close()

    def get_order(self, order_id: str) -> dict | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT order_id, sku_id, quantity, status, created_at FROM orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if row:
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"])
                return d
            return None
        finally:
            conn.close()

    def list_orders(self, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        conn = self._get_conn()
        try:
            total_row = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()
            total = total_row["count"]

            rows = conn.execute(
                "SELECT order_id, sku_id, quantity, status, created_at FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

            orders = []
            for row in rows:
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"])
                orders.append(d)

            return orders, total
        finally:
            conn.close()

    def confirm_order(self, order_id: str) -> dict:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE orders SET status = ? WHERE order_id = ?",
                    (OrderStatus.CONFIRMED.value, order_id),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT order_id, sku_id, quantity, status, created_at FROM orders WHERE order_id = ?",
                    (order_id,),
                ).fetchone()
                d = dict(row)
                d["created_at"] = datetime.fromisoformat(d["created_at"])
                return d
            finally:
                conn.close()
