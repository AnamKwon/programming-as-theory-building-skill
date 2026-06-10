import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class Repository:
    def __init__(self, db_path: str = "commerce.db"):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS skus (
                    sku_id TEXT PRIMARY KEY,
                    quantity INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    sku_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL DEFAULT 'CREATED',
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (sku_id) REFERENCES skus (sku_id)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    reservation_id TEXT NOT NULL,
                    sku_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL DEFAULT 'CREATED',
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    FOREIGN KEY (reservation_id) REFERENCES reservations (reservation_id),
                    FOREIGN KEY (sku_id) REFERENCES skus (sku_id)
                );

                CREATE INDEX IF NOT EXISTS idx_reservations_idempotency_key
                    ON reservations (idempotency_key);
                CREATE INDEX IF NOT EXISTS idx_orders_state
                    ON orders (state);
            """)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_sku(self, sku_id: str, quantity: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO skus (sku_id, quantity) VALUES (?, ?)",
                (sku_id, quantity),
            )

    def get_sku(self, sku_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sku_id, quantity FROM skus WHERE sku_id = ?",
                (sku_id,),
            ).fetchone()
        return dict(row) if row else None

    def adjust_stock(self, sku_id: str, delta: int) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT quantity FROM skus WHERE sku_id = ?",
                (sku_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"SKU {sku_id} not found")
            new_quantity = row["quantity"] + delta
            if new_quantity < 0:
                raise ValueError("Insufficient stock")
            conn.execute(
                "UPDATE skus SET quantity = ? WHERE sku_id = ?",
                (new_quantity, sku_id),
            )
        return {"sku_id": sku_id, "quantity": new_quantity}

    def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        idempotency_key: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO reservations
                   (reservation_id, sku_id, quantity, idempotency_key, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    reservation_id,
                    sku_id,
                    quantity,
                    idempotency_key,
                    created_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )

    def get_reservation(self, reservation_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT reservation_id, sku_id, quantity, state, created_at, expires_at
                   FROM reservations WHERE reservation_id = ?""",
                (reservation_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "reservation_id": row["reservation_id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "state": row["state"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "expires_at": datetime.fromisoformat(row["expires_at"]),
        }

    def get_reservation_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT reservation_id, sku_id, quantity, state, created_at, expires_at
                   FROM reservations WHERE idempotency_key = ?""",
                (idempotency_key,),
            ).fetchone()
        if not row:
            return None
        return {
            "reservation_id": row["reservation_id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "state": row["state"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "expires_at": datetime.fromisoformat(row["expires_at"]),
        }

    def update_reservation_state(self, reservation_id: str, state: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE reservations SET state = ? WHERE reservation_id = ?",
                (state, reservation_id),
            )

    def create_order(
        self,
        order_id: str,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        created_at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO orders
                   (order_id, reservation_id, sku_id, quantity, created_at, state)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (order_id, reservation_id, sku_id, quantity, created_at.isoformat(), "CREATED"),
            )

    def confirm_order(self, order_id: str, confirmed_at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET state = ?, confirmed_at = ? WHERE order_id = ?",
                ("CONFIRMED", confirmed_at.isoformat(), order_id),
            )

    def get_order(self, order_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT order_id, reservation_id, sku_id, quantity, state, created_at, confirmed_at
                   FROM orders WHERE order_id = ?""",
                (order_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "order_id": row["order_id"],
            "reservation_id": row["reservation_id"],
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "state": row["state"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "confirmed_at": datetime.fromisoformat(row["confirmed_at"]) if row["confirmed_at"] else None,
        }

    def list_orders(self, limit: int, offset: int) -> tuple[list[dict], int]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()["count"]
            rows = conn.execute(
                """SELECT order_id, reservation_id, sku_id, quantity, state, created_at, confirmed_at
                   FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        orders = []
        for row in rows:
            orders.append({
                "order_id": row["order_id"],
                "reservation_id": row["reservation_id"],
                "sku_id": row["sku_id"],
                "quantity": row["quantity"],
                "state": row["state"],
                "created_at": datetime.fromisoformat(row["created_at"]),
                "confirmed_at": datetime.fromisoformat(row["confirmed_at"]) if row["confirmed_at"] else None,
            })
        return orders, total

    def clear_all(self) -> None:
        """Used for testing only."""
        with self._connect() as conn:
            conn.executescript("""
                DELETE FROM orders;
                DELETE FROM reservations;
                DELETE FROM skus;
            """)
