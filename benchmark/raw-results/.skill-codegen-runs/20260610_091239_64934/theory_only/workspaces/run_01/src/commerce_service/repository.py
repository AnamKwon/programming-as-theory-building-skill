import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from commerce_service.models import Order, OrderState, Reservation, ReservationState, SKU


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skus (
                sku_id TEXT PRIMARY KEY,
                available_stock INTEGER NOT NULL,
                reserved_stock INTEGER NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                FOREIGN KEY (sku_id) REFERENCES skus (sku_id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                reservation_ids TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
                idempotency_key TEXT PRIMARY KEY,
                operation_type TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def create_sku(self, sku_id: str, initial_stock: int) -> SKU:
        self.conn.execute(
            "INSERT INTO skus (sku_id, available_stock, reserved_stock) VALUES (?, ?, ?)",
            (sku_id, initial_stock, 0),
        )
        self.conn.commit()
        return SKU(sku_id, initial_stock, 0)

    def get_sku(self, sku_id: str) -> Optional[SKU]:
        row = self.conn.execute(
            "SELECT sku_id, available_stock, reserved_stock FROM skus WHERE sku_id = ?",
            (sku_id,),
        ).fetchone()
        if not row:
            return None
        return SKU(row[0], row[1], row[2])

    def update_sku(self, sku: SKU) -> None:
        self.conn.execute(
            "UPDATE skus SET available_stock = ?, reserved_stock = ? WHERE sku_id = ?",
            (sku.available_stock, sku.reserved_stock, sku.sku_id),
        )
        self.conn.commit()

    def create_reservation(self, reservation: Reservation) -> None:
        self.conn.execute(
            """
            INSERT INTO reservations
            (reservation_id, sku_id, quantity, state, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                reservation.reservation_id,
                reservation.sku_id,
                reservation.quantity,
                reservation.state.value,
                reservation.created_at.isoformat(),
                reservation.expires_at.isoformat() if reservation.expires_at else None,
            ),
        )
        self.conn.commit()

    def get_reservation(self, reservation_id: str) -> Optional[Reservation]:
        row = self.conn.execute(
            """
            SELECT reservation_id, sku_id, quantity, state, created_at, expires_at
            FROM reservations WHERE reservation_id = ?
            """,
            (reservation_id,),
        ).fetchone()
        if not row:
            return None
        return Reservation(
            reservation_id=row[0],
            sku_id=row[1],
            quantity=row[2],
            state=ReservationState(row[3]),
            created_at=datetime.fromisoformat(row[4]),
            expires_at=datetime.fromisoformat(row[5]) if row[5] else None,
        )

    def update_reservation(self, reservation: Reservation) -> None:
        self.conn.execute(
            """
            UPDATE reservations
            SET state = ? WHERE reservation_id = ?
            """,
            (reservation.state.value, reservation.reservation_id),
        )
        self.conn.commit()

    def get_expired_reservations(self) -> list[Reservation]:
        now = datetime.utcnow().isoformat()
        rows = self.conn.execute(
            """
            SELECT reservation_id, sku_id, quantity, state, created_at, expires_at
            FROM reservations
            WHERE state = ? AND expires_at IS NOT NULL AND expires_at < ?
            """,
            (ReservationState.PENDING.value, now),
        ).fetchall()
        return [
            Reservation(
                reservation_id=row[0],
                sku_id=row[1],
                quantity=row[2],
                state=ReservationState(row[3]),
                created_at=datetime.fromisoformat(row[4]),
                expires_at=datetime.fromisoformat(row[5]) if row[5] else None,
            )
            for row in rows
        ]

    def create_order(self, order: Order) -> None:
        self.conn.execute(
            """
            INSERT INTO orders (order_id, reservation_ids, state, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                order.order_id,
                json.dumps(order.reservation_ids),
                order.state.value,
                order.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def get_order(self, order_id: str) -> Optional[Order]:
        row = self.conn.execute(
            """
            SELECT order_id, reservation_ids, state, created_at
            FROM orders WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()
        if not row:
            return None
        return Order(
            order_id=row[0],
            reservation_ids=json.loads(row[1]),
            state=OrderState(row[2]),
            created_at=datetime.fromisoformat(row[3]),
        )

    def update_order(self, order: Order) -> None:
        self.conn.execute(
            """
            UPDATE orders SET state = ? WHERE order_id = ?
            """,
            (order.state.value, order.order_id),
        )
        self.conn.commit()

    def list_orders(self, page: int = 1, page_size: int = 10) -> tuple[list[Order], int]:
        offset = (page - 1) * page_size
        total = self.conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        rows = self.conn.execute(
            """
            SELECT order_id, reservation_ids, state, created_at
            FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
        orders = [
            Order(
                order_id=row[0],
                reservation_ids=json.loads(row[1]),
                state=OrderState(row[2]),
                created_at=datetime.fromisoformat(row[3]),
            )
            for row in rows
        ]
        return orders, total

    def check_idempotency(self, idempotency_key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT result FROM idempotency WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return row[0] if row else None

    def record_idempotency(
        self, idempotency_key: str, operation_type: str, result: str
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO idempotency (idempotency_key, operation_type, result, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (idempotency_key, operation_type, result, datetime.utcnow().isoformat()),
        )
        self.conn.commit()
