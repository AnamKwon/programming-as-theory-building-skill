# Commerce Service

Inventory reservation and order orchestration API for a small commerce backend.

## Features

- SKU (stock keeping unit) management with stock levels
- Reservation system with expiration and idempotency
- Order creation from confirmed reservations
- API-key protected mutations
- Pagination support for order queries
- SQLite persistence

## Quick Start

### Install

```bash
pip install -e ".[dev]"
```

### Run

```bash
python -m commerce_service.app
```

Server starts on `http://localhost:8000`.

### Test

```bash
pytest tests/ -v
```

## API

### Health

`GET /health` — Health check.

### SKUs

`POST /skus` — Create a SKU (requires API key).

```json
{
  "sku_id": "SKU-001",
  "name": "Widget A",
  "initial_stock": 100
}
```

`POST /skus/{sku_id}/adjust-stock` — Adjust stock level (requires API key).

```json
{
  "delta": 10
}
```

### Reservations

`POST /reservations` — Reserve stock (idempotent via `idempotency_key`).

```json
{
  "sku_id": "SKU-001",
  "quantity": 5,
  "idempotency_key": "order-uuid-123"
}
```

`POST /reservations/{reservation_id}/confirm` — Confirm reservation and create order (requires API key).

`POST /reservations/{reservation_id}/cancel` — Cancel reservation (requires API key).

### Orders

`GET /orders` — List orders (paginated, requires API key).

Query parameters: `skip=0`, `limit=20`.

`GET /orders/{order_id}` — Get order details.

## Configuration

Set `API_KEY` environment variable for mutation endpoints. Default is `test-key`.

## Design

- **Models:** Pydantic for request/response validation.
- **Repository:** SQLAlchemy for database access.
- **Service:** Business logic with stock availability, idempotency, and expiration rules.
- **Security:** API-key dependency for protected endpoints.
