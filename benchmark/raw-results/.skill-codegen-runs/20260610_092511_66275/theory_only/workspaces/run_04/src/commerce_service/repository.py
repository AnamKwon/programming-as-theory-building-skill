import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import OrderResponse, OrderState, ReservationResponse, ReservationState, SKUResponse


class Repository:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        if db_path == ":memory:":
            db_file = Path(tempfile.gettempdir()) / f"commerce_service_{uuid.uuid4().hex}.db"
            self.db_path = str(db_file)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                sku_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                total_stock INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending',
                idempotency_key TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL UNIQUE,
                customer_id TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY (reservation_id) REFERENCES reservations(reservation_id),
                FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reservations_customer
            ON reservations(customer_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reservations_sku
            ON reservations(sku_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_customer
            ON orders(customer_id)
        """)

        conn.commit()
        conn.close()

    def create_sku(self, sku_id: str, name: str, initial_stock: int) -> SKUResponse:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO skus (sku_id, name, total_stock, created_at) VALUES (?, ?, ?, ?)",
                (sku_id, name, initial_stock, now),
            )
            conn.commit()
            return self.get_sku(sku_id)
        finally:
            conn.close()

    def get_sku(self, sku_id: str) -> Optional[SKUResponse]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,))
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM reservations WHERE sku_id = ? AND state = ?",
                (sku_id, ReservationState.PENDING.value),
            )
            reserved = cursor.fetchone()[0]
            available = row["total_stock"] - reserved

            return SKUResponse(
                sku_id=row["sku_id"],
                name=row["name"],
                total_stock=row["total_stock"],
                reserved_stock=reserved,
                available_stock=max(0, available),
            )
        finally:
            conn.close()

    def adjust_stock(self, sku_id: str, quantity_delta: int) -> SKUResponse:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skus SET total_stock = total_stock + ? WHERE sku_id = ?",
                (quantity_delta, sku_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"SKU {sku_id} not found")
            conn.commit()
            return self.get_sku(sku_id)
        finally:
            conn.close()

    def find_reservation_by_idempotency_key(
        self, customer_id: str, idempotency_key: str
    ) -> Optional[ReservationResponse]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM reservations WHERE customer_id = ? AND idempotency_key = ?",
                (customer_id, idempotency_key),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ReservationResponse(
                reservation_id=row["reservation_id"],
                customer_id=row["customer_id"],
                sku_id=row["sku_id"],
                quantity=row["quantity"],
                state=ReservationState(row["state"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
            )
        finally:
            conn.close()

    def create_reservation(
        self,
        customer_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        ttl_minutes: int = 15,
    ) -> ReservationResponse:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            reservation_id = str(uuid.uuid4())
            now = datetime.utcnow()
            expires_at = now + timedelta(minutes=ttl_minutes)

            cursor.execute(
                """INSERT INTO reservations
                   (reservation_id, customer_id, sku_id, quantity, state, idempotency_key, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    reservation_id,
                    customer_id,
                    sku_id,
                    quantity,
                    ReservationState.PENDING.value,
                    idempotency_key,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            conn.commit()
            return self.get_reservation(reservation_id)
        finally:
            conn.close()

    def get_reservation(self, reservation_id: str) -> Optional[ReservationResponse]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (reservation_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ReservationResponse(
                reservation_id=row["reservation_id"],
                customer_id=row["customer_id"],
                sku_id=row["sku_id"],
                quantity=row["quantity"],
                state=ReservationState(row["state"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
            )
        finally:
            conn.close()

    def update_reservation_state(
        self, reservation_id: str, new_state: ReservationState
    ) -> Optional[ReservationResponse]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reservations SET state = ? WHERE reservation_id = ?",
                (new_state.value, reservation_id),
            )
            if cursor.rowcount == 0:
                return None
            conn.commit()
            return self.get_reservation(reservation_id)
        finally:
            conn.close()

    def create_order(self, reservation: ReservationResponse) -> OrderResponse:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            order_id = str(uuid.uuid4())
            now = datetime.utcnow()

            cursor.execute(
                """INSERT INTO orders
                   (order_id, reservation_id, customer_id, sku_id, quantity, state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    order_id,
                    reservation.reservation_id,
                    reservation.customer_id,
                    reservation.sku_id,
                    reservation.quantity,
                    OrderState.CONFIRMED.value,
                    now.isoformat(),
                ),
            )
            conn.commit()
            return self.get_order(order_id)
        finally:
            conn.close()

    def get_order(self, order_id: str) -> Optional[OrderResponse]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return OrderResponse(
                order_id=row["order_id"],
                reservation_id=row["reservation_id"],
                customer_id=row["customer_id"],
                sku_id=row["sku_id"],
                quantity=row["quantity"],
                state=OrderState(row["state"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        finally:
            conn.close()

    def list_orders(self, limit: int = 10, offset: int = 0) -> tuple[list[OrderResponse], int]:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()

            orders = [
                OrderResponse(
                    order_id=row["order_id"],
                    reservation_id=row["reservation_id"],
                    customer_id=row["customer_id"],
                    sku_id=row["sku_id"],
                    quantity=row["quantity"],
                    state=OrderState(row["state"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]
            return orders, total
        finally:
            conn.close()
