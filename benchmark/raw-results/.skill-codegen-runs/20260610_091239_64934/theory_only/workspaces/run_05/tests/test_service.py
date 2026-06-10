import pytest
import sqlite3
from datetime import datetime, timedelta, timezone
from commerce_service.repository import Repository
from commerce_service.service import Service


@pytest.fixture
def db_connection():
    """Create a shared in-memory database for the test."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE skus (
            sku_id TEXT PRIMARY KEY,
            quantity INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE reservations (
            reservation_id TEXT PRIMARY KEY,
            sku_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'CREATED',
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES skus (sku_id)
        );

        CREATE TABLE orders (
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

        CREATE INDEX idx_reservations_idempotency_key
            ON reservations (idempotency_key);
        CREATE INDEX idx_orders_state
            ON orders (state);
    """)
    conn.commit()
    yield conn
    conn.close()


class InMemoryRepository(Repository):
    """Test repository that uses a shared connection."""
    def __init__(self, connection):
        self._shared_conn = connection
        self.db_path = ":memory:"

    def _connect(self):
        """Override to use shared connection."""
        class SharedConnContext:
            def __init__(self, conn):
                self.conn = conn
            def __enter__(self):
                return self.conn
            def __exit__(self, *args):
                self.conn.commit()
        return SharedConnContext(self._shared_conn)


@pytest.fixture
def repo(db_connection):
    return InMemoryRepository(db_connection)


@pytest.fixture
def service(repo):
    return Service(repo)


def test_create_sku(service):
    result = service.create_sku("SKU001", 100)
    assert result["sku_id"] == "SKU001"
    assert result["quantity"] == 100


def test_adjust_stock_increment(service):
    service.create_sku("SKU001", 50)
    result = service.adjust_stock("SKU001", 10)
    assert result["quantity"] == 60


def test_adjust_stock_decrement(service):
    service.create_sku("SKU001", 50)
    result = service.adjust_stock("SKU001", -20)
    assert result["quantity"] == 30


def test_adjust_stock_sku_not_found(service):
    with pytest.raises(ValueError, match="not found"):
        service.adjust_stock("NONEXISTENT", 10)


def test_adjust_stock_negative(service):
    service.create_sku("SKU001", 10)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.adjust_stock("SKU001", -20)


def test_create_reservation_success(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 25, "idempotent-key-1")

    assert res.sku_id == "SKU001"
    assert res.quantity == 25
    assert res.reservation_id is not None
    assert res.created_at is not None
    assert res.expires_at is not None


def test_create_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 10)
    with pytest.raises(ValueError, match="Insufficient stock"):
        service.create_reservation("SKU001", 50, "idempotent-key-1")


def test_create_reservation_sku_not_found(service):
    with pytest.raises(ValueError, match="not found"):
        service.create_reservation("NONEXISTENT", 10, "idempotent-key-1")


def test_create_reservation_idempotency(service):
    service.create_sku("SKU001", 100)
    res1 = service.create_reservation("SKU001", 25, "idempotent-key-1")
    res2 = service.create_reservation("SKU001", 25, "idempotent-key-1")

    assert res1.reservation_id == res2.reservation_id
    assert res1.created_at == res2.created_at


def test_create_reservation_different_keys_different_reservations(service):
    service.create_sku("SKU001", 100)
    res1 = service.create_reservation("SKU001", 25, "idempotent-key-1")
    res2 = service.create_reservation("SKU001", 25, "idempotent-key-2")

    assert res1.reservation_id != res2.reservation_id


def test_confirm_reservation_success(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 25, "idempotent-key-1")
    order = service.confirm_reservation(res.reservation_id)

    assert order.order_id is not None
    assert order.reservation_id == res.reservation_id
    assert order.state.value == "CONFIRMED"
    assert order.confirmed_at is not None


def test_confirm_reservation_not_found(service):
    with pytest.raises(ValueError, match="not found"):
        service.confirm_reservation("NONEXISTENT")


def test_confirm_reservation_insufficient_stock(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 50, "idempotent-key-1")

    service.adjust_stock("SKU001", -60)

    with pytest.raises(ValueError, match="Insufficient stock"):
        service.confirm_reservation(res.reservation_id)


def test_confirm_reservation_expired(service, repo):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 25, "idempotent-key-1")

    with repo._connect() as conn:
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        conn.execute(
            "UPDATE reservations SET expires_at = ? WHERE reservation_id = ?",
            (past, res.reservation_id),
        )

    with pytest.raises(ValueError, match="expired"):
        service.confirm_reservation(res.reservation_id)


def test_confirm_reservation_not_created_state(service, repo):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 25, "idempotent-key-1")
    service.confirm_reservation(res.reservation_id)

    with pytest.raises(ValueError, match="not in CREATED state"):
        service.confirm_reservation(res.reservation_id)


def test_cancel_reservation_success(service, repo):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 25, "idempotent-key-1")

    service.cancel_reservation(res.reservation_id)

    reservation = repo.get_reservation(res.reservation_id)
    assert reservation["state"] == "CANCELLED"


def test_cancel_reservation_not_found(service):
    with pytest.raises(ValueError, match="not found"):
        service.cancel_reservation("NONEXISTENT")


def test_cancel_reservation_not_created_state(service):
    service.create_sku("SKU001", 100)
    res = service.create_reservation("SKU001", 25, "idempotent-key-1")
    service.confirm_reservation(res.reservation_id)

    with pytest.raises(ValueError, match="not in CREATED state"):
        service.cancel_reservation(res.reservation_id)


def test_get_orders_empty(service):
    orders, total = service.get_orders(limit=10, offset=0)
    assert len(orders) == 0
    assert total == 0


def test_get_orders_pagination(service):
    service.create_sku("SKU001", 1000)

    for i in range(25):
        res = service.create_reservation("SKU001", 1, f"key-{i}")
        service.confirm_reservation(res.reservation_id)

    page1, total = service.get_orders(limit=10, offset=0)
    assert len(page1) == 10
    assert total == 25

    page2, _ = service.get_orders(limit=10, offset=10)
    assert len(page2) == 10

    page3, _ = service.get_orders(limit=10, offset=20)
    assert len(page3) == 5

    assert page1[0].order_id != page2[0].order_id
