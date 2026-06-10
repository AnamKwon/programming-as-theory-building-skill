import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from commerce_service.models import OrderItem, OrderResponse, ReservationResponse, SkuResponse


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skus (
                sku_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                current_stock INTEGER NOT NULL
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sku_id) REFERENCES skus (sku_id)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS order_items (
                item_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders (order_id),
                FOREIGN KEY (sku_id) REFERENCES skus (sku_id)
            )
        """
        )

        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_idempotency ON reservations(idempotency_key)"
        )

        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            conn = self._get_conn()
            conn.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False

    def create_sku(self, name: str, price: float, stock: int = 0) -> SkuResponse:
        """Create a new SKU."""
        sku_id = str(uuid.uuid4())
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO skus (sku_id, name, price, current_stock) VALUES (?, ?, ?, ?)",
            (sku_id, name, price, stock),
        )

        conn.commit()
        conn.close()

        return SkuResponse(sku_id=sku_id, name=name, price=price, current_stock=stock)

    def get_sku(self, sku_id: str) -> Optional[SkuResponse]:
        """Get SKU by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return SkuResponse(
            sku_id=row["sku_id"],
            name=row["name"],
            price=row["price"],
            current_stock=row["current_stock"],
        )

    def adjust_stock(self, sku_id: str, quantity: int) -> Optional[SkuResponse]:
        """Adjust stock for a SKU."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE skus SET current_stock = current_stock + ? WHERE sku_id = ?",
            (quantity, sku_id),
        )

        if cursor.rowcount == 0:
            conn.close()
            return None

        cursor.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,))
        row = cursor.fetchone()
        conn.commit()
        conn.close()

        return SkuResponse(
            sku_id=row["sku_id"],
            name=row["name"],
            price=row["price"],
            current_stock=row["current_stock"],
        )

    def reserve(
        self, sku_id: str, quantity: int, idempotency_key: str, expiry_minutes: int = 15
    ) -> Optional[ReservationResponse]:
        """Create a reservation. Returns existing reservation if idempotency key matches."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?", (idempotency_key,)
        )
        existing = cursor.fetchone()

        if existing:
            conn.close()
            return ReservationResponse(
                reservation_id=existing["reservation_id"],
                sku_id=existing["sku_id"],
                quantity=existing["quantity"],
                status=existing["status"],
                expires_at=datetime.fromisoformat(existing["expires_at"]),
                idempotency_key=existing["idempotency_key"],
            )

        reservation_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=expiry_minutes)

        cursor.execute(
            """
            INSERT INTO reservations
            (reservation_id, sku_id, quantity, status, expires_at, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                reservation_id,
                sku_id,
                quantity,
                "RESERVED",
                expires_at.isoformat(),
                idempotency_key,
                now.isoformat(),
            ),
        )

        conn.commit()
        conn.close()

        return ReservationResponse(
            reservation_id=reservation_id,
            sku_id=sku_id,
            quantity=quantity,
            status="RESERVED",
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

    def get_reservation(self, reservation_id: str) -> Optional[ReservationResponse]:
        """Get reservation by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (reservation_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return ReservationResponse(
            reservation_id=row["reservation_id"],
            sku_id=row["sku_id"],
            quantity=row["quantity"],
            status=row["status"],
            expires_at=datetime.fromisoformat(row["expires_at"]),
            idempotency_key=row["idempotency_key"],
        )

    def confirm_reservation(self, reservation_id: str) -> Optional[str]:
        """Confirm a reservation and create an order. Returns order_id if successful."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (reservation_id,))
        reservation = cursor.fetchone()

        if not reservation:
            conn.close()
            return None

        if reservation["status"] != "RESERVED":
            conn.close()
            return None

        expires_at = datetime.fromisoformat(reservation["expires_at"])
        if datetime.utcnow() > expires_at:
            conn.close()
            return None

        order_id = str(uuid.uuid4())
        now = datetime.utcnow()

        cursor.execute(
            "INSERT INTO orders (order_id, status, created_at) VALUES (?, ?, ?)",
            (order_id, "CONFIRMED", now.isoformat()),
        )

        cursor.execute("SELECT * FROM skus WHERE sku_id = ?", (reservation["sku_id"],))
        sku = cursor.fetchone()

        item_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO order_items (item_id, order_id, sku_id, quantity, price)
            VALUES (?, ?, ?, ?, ?)
        """,
            (item_id, order_id, reservation["sku_id"], reservation["quantity"], sku["price"]),
        )

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE reservation_id = ?",
            ("CONFIRMED", reservation_id),
        )

        conn.commit()
        conn.close()

        return order_id

    def cancel_reservation(self, reservation_id: str) -> bool:
        """Cancel a reservation."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE reservation_id = ? AND status = ?",
            ("CANCELLED", reservation_id, "RESERVED"),
        )

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected > 0

    def get_order(self, order_id: str) -> Optional[OrderResponse]:
        """Get order by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        order = cursor.fetchone()

        if not order:
            conn.close()
            return None

        cursor.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY item_id", (order_id,)
        )
        items = cursor.fetchall()
        conn.close()

        order_items = [
            OrderItem(sku_id=item["sku_id"], quantity=item["quantity"], price=item["price"])
            for item in items
        ]

        return OrderResponse(
            order_id=order["order_id"],
            status=order["status"],
            items=order_items,
            created_at=datetime.fromisoformat(order["created_at"]),
        )

    def list_orders(self, skip: int = 0, limit: int = 10) -> tuple[list[OrderResponse], int]:
        """List orders with pagination."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, skip),
        )
        orders = cursor.fetchall()

        result = []
        for order in orders:
            cursor.execute(
                "SELECT * FROM order_items WHERE order_id = ? ORDER BY item_id",
                (order["order_id"],),
            )
            items = cursor.fetchall()

            order_items = [
                OrderItem(sku_id=item["sku_id"], quantity=item["quantity"], price=item["price"])
                for item in items
            ]

            result.append(
                OrderResponse(
                    order_id=order["order_id"],
                    status=order["status"],
                    items=order_items,
                    created_at=datetime.fromisoformat(order["created_at"]),
                )
            )

        conn.close()

        return result, total
