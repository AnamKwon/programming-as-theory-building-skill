import json
import sqlite3
from datetime import datetime
from typing import Optional

from .models import (
    DBOrder,
    DBOrderItem,
    DBReservation,
    DBSku,
    OrderStatus,
    ReservationStatus,
)


class Repository:
    def __init__(self, db_path: str = "./commerce.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skus (
                sku TEXT PRIMARY KEY,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                FOREIGN KEY(sku) REFERENCES skus(sku)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                items_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        )

        conn.commit()
        conn.close()

    def create_sku(self, sku: str, quantity: int) -> DBSku:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            "INSERT INTO skus (sku, quantity, created_at) VALUES (?, ?, ?)",
            (sku, quantity, now),
        )
        conn.commit()
        conn.close()

        return DBSku(sku=sku, quantity=quantity, created_at=datetime.fromisoformat(now))

    def get_sku(self, sku: str) -> Optional[DBSku]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return DBSku(
            sku=row["sku"],
            quantity=row["quantity"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def update_sku_quantity(self, sku: str, new_quantity: int) -> Optional[DBSku]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT created_at FROM skus WHERE sku = ?", (sku,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        cursor.execute("UPDATE skus SET quantity = ? WHERE sku = ?", (new_quantity, sku))
        conn.commit()
        conn.close()

        return DBSku(
            sku=sku,
            quantity=new_quantity,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create_reservation(
        self,
        reservation_id: str,
        sku: str,
        quantity: int,
        expires_at: datetime,
        idempotency_key: str,
    ) -> DBReservation:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO reservations
            (reservation_id, sku, quantity, status, expires_at, created_at, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reservation_id,
                sku,
                quantity,
                ReservationStatus.PENDING.value,
                expires_at.isoformat(),
                now,
                idempotency_key,
            ),
        )
        conn.commit()
        conn.close()

        return DBReservation(
            reservation_id=reservation_id,
            sku=sku,
            quantity=quantity,
            status=ReservationStatus.PENDING,
            expires_at=expires_at,
            created_at=datetime.fromisoformat(now),
            idempotency_key=idempotency_key,
        )

    def get_reservation(self, reservation_id: str) -> Optional[DBReservation]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM reservations WHERE reservation_id = ?", (reservation_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return DBReservation(
            reservation_id=row["reservation_id"],
            sku=row["sku"],
            quantity=row["quantity"],
            status=ReservationStatus(row["status"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            idempotency_key=row["idempotency_key"],
        )

    def get_reservation_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[DBReservation]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM reservations WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return DBReservation(
            reservation_id=row["reservation_id"],
            sku=row["sku"],
            quantity=row["quantity"],
            status=ReservationStatus(row["status"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            idempotency_key=row["idempotency_key"],
        )

    def update_reservation_status(
        self, reservation_id: str, status: ReservationStatus
    ) -> Optional[DBReservation]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM reservations WHERE reservation_id = ?", (reservation_id,)
        )
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        cursor.execute(
            "UPDATE reservations SET status = ? WHERE reservation_id = ?",
            (status.value, reservation_id),
        )
        conn.commit()
        conn.close()

        return DBReservation(
            reservation_id=row["reservation_id"],
            sku=row["sku"],
            quantity=row["quantity"],
            status=status,
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            idempotency_key=row["idempotency_key"],
        )

    def create_order(
        self, order_id: str, items: list[DBOrderItem]
    ) -> DBOrder:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        items_json = json.dumps([{"sku": item.sku, "quantity": item.quantity} for item in items])

        cursor.execute(
            """
            INSERT INTO orders (order_id, status, items_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                order_id,
                OrderStatus.PENDING.value,
                items_json,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()

        return DBOrder(
            order_id=order_id,
            status=OrderStatus.PENDING,
            items=items,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
        )

    def get_order(self, order_id: str) -> Optional[DBOrder]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        items = [
            DBOrderItem(sku=item["sku"], quantity=item["quantity"])
            for item in json.loads(row["items_json"])
        ]

        return DBOrder(
            order_id=row["order_id"],
            status=OrderStatus(row["status"]),
            items=items,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_orders(self, cursor: Optional[str] = None, limit: int = 20) -> tuple[list[DBOrder], Optional[str]]:
        conn = self._get_conn()
        cursor_conn = conn.cursor()

        offset = 0
        if cursor:
            try:
                offset = int(cursor)
            except ValueError:
                offset = 0

        cursor_conn.execute(
            """
            SELECT * FROM orders
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit + 1, offset),
        )
        rows = cursor_conn.fetchall()
        conn.close()

        orders = []
        next_cursor = None

        for i, row in enumerate(rows):
            if i >= limit:
                next_cursor = str(offset + limit)
                break

            items = [
                DBOrderItem(sku=item["sku"], quantity=item["quantity"])
                for item in json.loads(row["items_json"])
            ]

            orders.append(
                DBOrder(
                    order_id=row["order_id"],
                    status=OrderStatus(row["status"]),
                    items=items,
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
            )

        return orders, next_cursor

    def update_order_status(
        self, order_id: str, status: OrderStatus
    ) -> Optional[DBOrder]:
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        now = datetime.utcnow().isoformat()
        cursor.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
            (status.value, now, order_id),
        )
        conn.commit()
        conn.close()

        items = [
            DBOrderItem(sku=item["sku"], quantity=item["quantity"])
            for item in json.loads(row["items_json"])
        ]

        return DBOrder(
            order_id=row["order_id"],
            status=status,
            items=items,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(now),
        )
