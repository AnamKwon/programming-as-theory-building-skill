"""Repository layer for database access."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Order, Reservation, ReservationStatus, SKU


class Repository:
    """Data access layer using SQLite."""

    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Initialize database schema on startup."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT NOT NULL,
                    available_stock INTEGER NOT NULL,
                    reserved_stock INTEGER NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL,
                    sku_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(reservation_id),
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id),
                    FOREIGN KEY (sku_id) REFERENCES skus(id)
                )
                """
            )
            conn.commit()

    def create_sku(self, product_name: str, initial_stock: int) -> SKU:
        """Create a new SKU."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO skus (product_name, available_stock, reserved_stock) VALUES (?, ?, ?)",
                (product_name, initial_stock, 0),
            )
            conn.commit()
            sku_id = cursor.lastrowid
            return SKU(sku_id, product_name, initial_stock, 0)

    def get_sku(self, sku_id: int) -> Optional[SKU]:
        """Retrieve a SKU by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, product_name, available_stock, reserved_stock FROM skus WHERE id = ?",
                (sku_id,),
            ).fetchone()
            if row:
                return SKU(row["id"], row["product_name"], row["available_stock"], row["reserved_stock"])
            return None

    def update_sku_stock(self, sku_id: int, available_delta: int, reserved_delta: int) -> bool:
        """Update SKU stock levels. Returns True if successful."""
        with self._get_connection() as conn:
            result = conn.execute(
                """
                UPDATE skus
                SET available_stock = available_stock + ?,
                    reserved_stock = reserved_stock + ?
                WHERE id = ?
                """,
                (available_delta, reserved_delta, sku_id),
            )
            conn.commit()
            return result.rowcount > 0

    def create_reservation(
        self,
        sku_id: int,
        quantity: int,
        idempotency_key: str,
        expires_at: datetime,
    ) -> Reservation:
        """Create a new reservation."""
        with self._get_connection() as conn:
            created_at = datetime.utcnow()
            cursor = conn.execute(
                """
                INSERT INTO reservations (sku_id, quantity, status, idempotency_key, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sku_id,
                    quantity,
                    ReservationStatus.PENDING.value,
                    idempotency_key,
                    expires_at.isoformat(),
                    created_at.isoformat(),
                ),
            )
            conn.commit()
            return Reservation(
                cursor.lastrowid, sku_id, quantity, ReservationStatus.PENDING, idempotency_key, expires_at, created_at
            )

    def get_reservation(self, reservation_id: int) -> Optional[Reservation]:
        """Retrieve a reservation by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, idempotency_key, expires_at, created_at
                FROM reservations WHERE id = ?
                """,
                (reservation_id,),
            ).fetchone()
            if row:
                return Reservation(
                    row["id"],
                    row["sku_id"],
                    row["quantity"],
                    ReservationStatus(row["status"]),
                    row["idempotency_key"],
                    datetime.fromisoformat(row["expires_at"]),
                    datetime.fromisoformat(row["created_at"]),
                )
            return None

    def get_reservation_by_idempotency_key(self, key: str) -> Optional[Reservation]:
        """Retrieve a reservation by idempotency key."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, sku_id, quantity, status, idempotency_key, expires_at, created_at
                FROM reservations WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()
            if row:
                return Reservation(
                    row["id"],
                    row["sku_id"],
                    row["quantity"],
                    ReservationStatus(row["status"]),
                    row["idempotency_key"],
                    datetime.fromisoformat(row["expires_at"]),
                    datetime.fromisoformat(row["created_at"]),
                )
            return None

    def update_reservation_status(self, reservation_id: int, status: ReservationStatus) -> bool:
        """Update reservation status."""
        with self._get_connection() as conn:
            result = conn.execute(
                "UPDATE reservations SET status = ? WHERE id = ?",
                (status.value, reservation_id),
            )
            conn.commit()
            return result.rowcount > 0

    def create_order(
        self,
        reservation_id: int,
        sku_id: int,
        quantity: int,
    ) -> Order:
        """Create an order from a confirmed reservation."""
        with self._get_connection() as conn:
            created_at = datetime.utcnow()
            cursor = conn.execute(
                """
                INSERT INTO orders (reservation_id, sku_id, quantity, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (reservation_id, sku_id, quantity, ReservationStatus.CONFIRMED.value, created_at.isoformat()),
            )
            conn.commit()
            return Order(cursor.lastrowid, reservation_id, sku_id, quantity, ReservationStatus.CONFIRMED, created_at)

    def get_orders(self, limit: int = 10, cursor: Optional[int] = None) -> tuple[list[Order], Optional[int]]:
        """Get orders with pagination. Returns (orders, next_cursor)."""
        with self._get_connection() as conn:
            query = "SELECT id, reservation_id, sku_id, quantity, status, created_at FROM orders"
            params = []

            if cursor:
                query += " WHERE id > ?"
                params.append(cursor)

            query += " ORDER BY id ASC LIMIT ?"
            params.append(limit + 1)

            rows = conn.execute(query, params).fetchall()

            orders = []
            next_cursor = None

            for i, row in enumerate(rows):
                if i < limit:
                    orders.append(
                        Order(
                            row["id"],
                            row["reservation_id"],
                            row["sku_id"],
                            row["quantity"],
                            ReservationStatus(row["status"]),
                            datetime.fromisoformat(row["created_at"]),
                        )
                    )
                else:
                    next_cursor = rows[limit - 1]["id"]
                    break

            return orders, next_cursor

    def get_order_by_reservation_id(self, reservation_id: int) -> Optional[Order]:
        """Retrieve an order by reservation ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, reservation_id, sku_id, quantity, status, created_at FROM orders WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if row:
                return Order(
                    row["id"],
                    row["reservation_id"],
                    row["sku_id"],
                    row["quantity"],
                    ReservationStatus(row["status"]),
                    datetime.fromisoformat(row["created_at"]),
                )
            return None
