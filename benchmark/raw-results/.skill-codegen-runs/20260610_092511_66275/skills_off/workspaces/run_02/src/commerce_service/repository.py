import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .models import ReservationState, OrderState


class Database:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skus (
                    sku TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    sku TEXT PRIMARY KEY,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sku) REFERENCES skus(sku)
                )
            """)
            conn.commit()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def create_sku(self, sku: str, name: str) -> bool:
        try:
            with self._connection() as conn:
                conn.execute("INSERT INTO skus (sku, name) VALUES (?, ?)", (sku, name))
                conn.execute("INSERT INTO inventory (sku, quantity) VALUES (?, ?)", (sku, 0))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_sku(self, sku: str) -> dict | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM skus WHERE sku = ?", (sku,)).fetchone()
            return dict(row) if row else None

    def adjust_inventory(self, sku: str, quantity: int) -> dict | None:
        with self._connection() as conn:
            current = conn.execute(
                "SELECT quantity FROM inventory WHERE sku = ?", (sku,)
            ).fetchone()
            if not current:
                return None
            new_qty = current["quantity"] + quantity
            conn.execute("UPDATE inventory SET quantity = ? WHERE sku = ?", (new_qty, sku))
            conn.commit()
            return {"sku": sku, "quantity": new_qty}

    def get_inventory(self, sku: str) -> int | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT quantity FROM inventory WHERE sku = ?", (sku,)
            ).fetchone()
            return row["quantity"] if row else None

    def create_reservation(self, sku: str, quantity: int, idempotency_key: str) -> dict | None:
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        try:
            with self._connection() as conn:
                conn.execute(
                    """INSERT INTO reservations
                       (sku, quantity, state, idempotency_key, expires_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (sku, quantity, ReservationState.PENDING, idempotency_key, expires_at),
                )
                conn.commit()
                reservation_id = conn.lastrowid
            return self.get_reservation(reservation_id)
        except sqlite3.IntegrityError:
            # Idempotency: return existing reservation
            return self.get_reservation_by_key(idempotency_key)

    def get_reservation(self, reservation_id: int) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM reservations WHERE id = ?", (reservation_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_reservation_by_key(self, idempotency_key: str) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM reservations WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            return dict(row) if row else None

    def update_reservation_state(self, reservation_id: int, state: str) -> bool:
        with self._connection() as conn:
            conn.execute(
                "UPDATE reservations SET state = ? WHERE id = ?", (state, reservation_id)
            )
            conn.commit()
        return True

    def list_pending_reservations(self) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM reservations WHERE state = ?", (ReservationState.PENDING,)
            ).fetchall()
            return [dict(row) for row in rows]

    def create_order(self, sku: str, quantity: int) -> dict | None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO orders (sku, quantity, state) VALUES (?, ?, ?)",
                (sku, quantity, OrderState.PENDING),
            )
            conn.commit()
            order_id = conn.lastrowid
        return self.get_order(order_id)

    def get_order(self, order_id: int) -> dict | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            return dict(row) if row else None

    def update_order_state(self, order_id: int, state: str) -> bool:
        with self._connection() as conn:
            conn.execute("UPDATE orders SET state = ? WHERE id = ?", (state, order_id))
            conn.commit()
        return True

    def list_orders(self, skip: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        with self._connection() as conn:
            total = conn.execute("SELECT COUNT(*) as count FROM orders").fetchone()["count"]
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, skip),
            ).fetchall()
            return [dict(row) for row in rows], total
