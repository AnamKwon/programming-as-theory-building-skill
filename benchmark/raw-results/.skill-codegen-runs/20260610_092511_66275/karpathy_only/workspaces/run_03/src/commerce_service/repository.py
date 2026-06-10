import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from commerce_service.models import ReservationStatus


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                sku TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                available_stock INTEGER NOT NULL,
                reserved_stock INTEGER NOT NULL DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                order_id TEXT,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus (sku),
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (sku) REFERENCES skus (sku)
            )
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, name: str, initial_stock: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO skus (sku, name, available_stock, reserved_stock)
                VALUES (?, ?, ?, 0)
                """,
                (sku, name, initial_stock),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_sku(self, sku: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def adjust_stock(self, sku: str, quantity: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE skus
                SET available_stock = available_stock + ?
                WHERE sku = ?
                """,
                (quantity, sku),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return False
            return True
        finally:
            conn.close()

    def create_reservation(
        self, sku: str, quantity: int, idempotency_key: str, ttl_minutes: int = 30
    ) -> Optional[str]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            reservation_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            expires_at = (
                datetime.utcnow() + timedelta(minutes=ttl_minutes)
            ).isoformat()

            cursor.execute(
                """
                INSERT INTO reservations (id, sku, quantity, status, idempotency_key, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation_id,
                    sku,
                    quantity,
                    ReservationStatus.PENDING.value,
                    idempotency_key,
                    expires_at,
                    now,
                ),
            )
            conn.commit()
            return reservation_id
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    def get_reservation(self, reservation_id: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status.value, reservation_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def set_reservation_order(self, reservation_id: str, order_id: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE reservations SET order_id = ? WHERE id = ?",
                (order_id, reservation_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def create_order(self, sku: str, quantity: int) -> str:
        conn = self._get_connection()
        cursor = conn.cursor()
        order_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO orders (id, sku, quantity, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (order_id, sku, quantity, "completed", now, now),
        )
        conn.commit()
        conn.close()
        return order_id

    def get_order(self, order_id: str) -> Optional[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        cursor.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, skip),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows], total

    def reserve_stock(self, sku: str, quantity: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE skus
                SET available_stock = available_stock - ?,
                    reserved_stock = reserved_stock + ?
                WHERE sku = ? AND available_stock >= ?
                """,
                (quantity, quantity, sku, quantity),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def release_reserved_stock(self, sku: str, quantity: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE skus
                SET available_stock = available_stock + ?,
                    reserved_stock = reserved_stock - ?
                WHERE sku = ?
                """,
                (quantity, quantity, sku),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def confirm_reservation_stock(self, sku: str, quantity: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE skus
                SET reserved_stock = reserved_stock - ?
                WHERE sku = ?
                """,
                (quantity, sku),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def clean_expired_reservations(self) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            SELECT id, sku, quantity FROM reservations
            WHERE status = ? AND expires_at < ?
            """,
            (ReservationStatus.PENDING.value, now),
        )
        expired = cursor.fetchall()

        for row in expired:
            self.release_reserved_stock(row["sku"], row["quantity"])
            cursor.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (ReservationStatus.EXPIRED.value, row["id"]),
            )

        conn.commit()
        conn.close()
        return len(expired)
