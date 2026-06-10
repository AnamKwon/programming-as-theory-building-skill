"""Database repository for commerce service."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import Order, Reservation, ReservationState, SKU


class Repository:
    """SQLite database repository for inventory and orders."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skus (
                id TEXT PRIMARY KEY,
                quantity INTEGER NOT NULL
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                FOREIGN KEY (sku_id) REFERENCES skus(id)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                reservation_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(id),
                FOREIGN KEY (reservation_id) REFERENCES reservations(id)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key TEXT PRIMARY KEY,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """
        )

        self.conn.commit()

    def create_sku(self, sku_id: str, quantity: int) -> SKU:
        """Create a new SKU."""
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO skus (id, quantity) VALUES (?, ?)", (sku_id, quantity))
        self.conn.commit()
        return SKU(id=sku_id, quantity=quantity)

    def get_sku(self, sku_id: str) -> Optional[SKU]:
        """Get SKU by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, quantity FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        if row:
            return SKU(id=row["id"], quantity=row["quantity"])
        return None

    def adjust_stock(self, sku_id: str, delta: int) -> Optional[SKU]:
        """Adjust stock quantity."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT quantity FROM skus WHERE id = ?", (sku_id,))
        row = cursor.fetchone()
        if not row:
            return None

        new_quantity = row["quantity"] + delta
        cursor.execute("UPDATE skus SET quantity = ? WHERE id = ?", (new_quantity, sku_id))
        self.conn.commit()
        return SKU(id=sku_id, quantity=new_quantity)

    def create_reservation(
        self, reservation_id: str, sku_id: str, quantity: int, idempotency_key: str, ttl_minutes: int = 15
    ) -> Reservation:
        """Create a new reservation."""
        cursor = self.conn.cursor()
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=ttl_minutes)

        cursor.execute(
            """
            INSERT INTO reservations
            (id, sku_id, quantity, state, created_at, expires_at, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                reservation_id,
                sku_id,
                quantity,
                ReservationState.PENDING.value,
                now.isoformat(),
                expires_at.isoformat(),
                idempotency_key,
            ),
        )
        self.conn.commit()

        return Reservation(
            id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            state=ReservationState.PENDING,
            created_at=now,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

    def get_reservation(self, reservation_id: str) -> Optional[Reservation]:
        """Get reservation by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, sku_id, quantity, state, created_at, expires_at, idempotency_key
            FROM reservations WHERE id = ?
        """,
            (reservation_id,),
        )
        row = cursor.fetchone()
        if row:
            return Reservation(
                id=row["id"],
                sku_id=row["sku_id"],
                quantity=row["quantity"],
                state=ReservationState(row["state"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                idempotency_key=row["idempotency_key"],
            )
        return None

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> Optional[Reservation]:
        """Get reservation by idempotency key."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, sku_id, quantity, state, created_at, expires_at, idempotency_key
            FROM reservations WHERE idempotency_key = ?
        """,
            (idempotency_key,),
        )
        row = cursor.fetchone()
        if row:
            return Reservation(
                id=row["id"],
                sku_id=row["sku_id"],
                quantity=row["quantity"],
                state=ReservationState(row["state"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                idempotency_key=row["idempotency_key"],
            )
        return None

    def update_reservation_state(self, reservation_id: str, state: ReservationState) -> Optional[Reservation]:
        """Update reservation state."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE reservations SET state = ? WHERE id = ?", (state.value, reservation_id)
        )
        self.conn.commit()

        return self.get_reservation(reservation_id)

    def create_order(self, order_id: str, sku_id: str, quantity: int, reservation_id: str) -> Order:
        """Create a new order."""
        cursor = self.conn.cursor()
        now = datetime.utcnow()

        cursor.execute(
            """
            INSERT INTO orders (id, sku_id, quantity, reservation_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (order_id, sku_id, quantity, reservation_id, now.isoformat()),
        )
        self.conn.commit()

        return Order(id=order_id, sku_id=sku_id, quantity=quantity, reservation_id=reservation_id, created_at=now)

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, sku_id, quantity, reservation_id, created_at FROM orders WHERE id = ?
        """,
            (order_id,),
        )
        row = cursor.fetchone()
        if row:
            return Order(
                id=row["id"],
                sku_id=row["sku_id"],
                quantity=row["quantity"],
                reservation_id=row["reservation_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        return None

    def list_orders(self, limit: int = 20, offset: int = 0) -> tuple[int, list[Order]]:
        """List orders with pagination."""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT id, sku_id, quantity, reservation_id, created_at FROM orders
            ORDER BY created_at DESC LIMIT ? OFFSET ?
        """,
            (limit, offset),
        )
        rows = cursor.fetchall()

        orders = [
            Order(
                id=row["id"],
                sku_id=row["sku_id"],
                quantity=row["quantity"],
                reservation_id=row["reservation_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

        return total, orders

    def close(self):
        """Close database connection."""
        self.conn.close()
