import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._shared_connection = None
        if db_path == ":memory:":
            self._shared_connection = sqlite3.connect(db_path, check_same_thread=False)
            self._shared_connection.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_connection is not None:
            return self._shared_connection
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _should_close_connection(self, conn: sqlite3.Connection) -> bool:
        return self._shared_connection is None or conn is not self._shared_connection

    def _init_db(self) -> None:
        conn = self._get_connection()
        should_close = self._shared_connection is None
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    sku TEXT PRIMARY KEY,
                    on_hand INTEGER NOT NULL DEFAULT 0,
                    reserved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    sku TEXT NOT NULL,
                    units INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    sku TEXT NOT NULL,
                    units INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reservations_idempotency
                ON reservations(idempotency_key, sku)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_created
                ON orders(created_at DESC)
            """)
            conn.commit()
        finally:
            if should_close:
                conn.close()

    def create_sku(self, sku: str, initial_stock: int) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO skus (sku, on_hand, reserved, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (sku, initial_stock, 0, datetime.utcnow().isoformat()),
            )
            conn.commit()
        finally:
            if self._should_close_connection(conn):
                conn.close()

    def adjust_stock(self, sku: str, quantity: int) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE skus SET on_hand = on_hand + ? WHERE sku = ?
                """,
                (quantity, sku),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"SKU {sku} not found")
            conn.commit()
        finally:
            if self._should_close_connection(conn):
                conn.close()

    def get_sku(self, sku: str) -> Optional[Tuple[int, int]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT on_hand, reserved FROM skus WHERE sku = ?", (sku,)
            )
            row = cursor.fetchone()
            if row:
                return (row[0], row[1])
            return None
        finally:
            if self._should_close_connection(conn):
                conn.close()

    def create_reservation(
        self, sku: str, units: int, idempotency_key: str
    ) -> Tuple[str, datetime]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")

            # Check if a reservation with this idempotency key already exists
            cursor.execute(
                "SELECT reservation_id, expires_at FROM reservations WHERE idempotency_key = ? AND sku = ?",
                (idempotency_key, sku),
            )
            existing = cursor.fetchone()
            if existing:
                conn.commit()
                return (existing[0], datetime.fromisoformat(existing[1]))

            cursor.execute(
                "SELECT on_hand, reserved FROM skus WHERE sku = ?",
                (sku,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"SKU {sku} not found")

            on_hand, reserved = row[0], row[1]
            if on_hand < units:
                raise ValueError(
                    f"Insufficient stock. Available: {on_hand}, Requested: {units}"
                )

            reservation_id_str = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            expires_at = (datetime.utcnow() + timedelta(seconds=30)).isoformat()

            cursor.execute(
                """
                INSERT INTO reservations
                (reservation_id, sku, units, state, idempotency_key, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation_id_str,
                    sku,
                    units,
                    "pending",
                    idempotency_key,
                    now,
                    expires_at,
                ),
            )

            cursor.execute(
                "UPDATE skus SET reserved = reserved + ? WHERE sku = ?",
                (units, sku),
            )

            conn.commit()
            return (reservation_id_str, datetime.fromisoformat(expires_at))
        except Exception:
            conn.rollback()
            raise
        finally:
            if self._should_close_connection(conn):
                conn.close()

    def get_reservation(self, reservation_id: str) -> Optional[dict]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT reservation_id, sku, units, state, created_at, expires_at FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "reservation_id": row[0],
                    "sku": row[1],
                    "units": row[2],
                    "state": row[3],
                    "created_at": datetime.fromisoformat(row[4]),
                    "expires_at": datetime.fromisoformat(row[5]),
                }
            return None
        finally:
            if self._should_close_connection(conn):
                conn.close()

    def confirm_reservation(self, reservation_id: str) -> str:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")

            cursor.execute(
                "SELECT sku, units, state, expires_at FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Reservation {reservation_id} not found")

            sku, units, state, expires_at_str = row
            if state != "pending":
                raise ValueError(f"Cannot confirm reservation in state: {state}")

            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() > expires_at:
                raise ValueError("Reservation has expired")

            order_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                INSERT INTO orders (order_id, sku, units, created_at, confirmed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, sku, units, now, now),
            )

            cursor.execute(
                "UPDATE reservations SET state = ? WHERE reservation_id = ?",
                ("confirmed", reservation_id),
            )

            cursor.execute(
                "UPDATE skus SET reserved = reserved - ? WHERE sku = ?",
                (units, sku),
            )

            conn.commit()
            return order_id
        except Exception:
            conn.rollback()
            raise
        finally:
            if self._should_close_connection(conn):
                conn.close()

    def cancel_reservation(self, reservation_id: str) -> None:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")

            cursor.execute(
                "SELECT sku, units, state FROM reservations WHERE reservation_id = ?",
                (reservation_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Reservation {reservation_id} not found")

            sku, units, state = row
            if state != "pending":
                raise ValueError(f"Cannot cancel reservation in state: {state}")

            cursor.execute(
                "UPDATE reservations SET state = ? WHERE reservation_id = ?",
                ("cancelled", reservation_id),
            )

            cursor.execute(
                "UPDATE skus SET reserved = reserved - ? WHERE sku = ?",
                (units, sku),
            )

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if self._should_close_connection(conn):
                conn.close()

    def get_orders(self, limit: int = 10, offset: int = 0) -> List[dict]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT order_id, sku, units, created_at, confirmed_at
                FROM orders
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = cursor.fetchall()
            return [
                {
                    "order_id": row[0],
                    "sku": row[1],
                    "units": row[2],
                    "created_at": datetime.fromisoformat(row[3]),
                    "confirmed_at": datetime.fromisoformat(row[4]),
                }
                for row in rows
            ]
        finally:
            if self._should_close_connection(conn):
                conn.close()

    def get_total_orders(self) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders")
            count = cursor.fetchone()[0]
            return count
        finally:
            if self._should_close_connection(conn):
                conn.close()
