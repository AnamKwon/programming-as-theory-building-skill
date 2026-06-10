# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create products and manage inventory
- **Reservations**: Hold inventory for customers with automatic expiration
- **Orders**: Convert reservations into confirmed orders
- **Pagination**: Efficient order lookup with cursor-based pagination
- **Idempotency**: Safe retry of reservation creation using idempotency keys
- **API Key Authentication**: Secure mutating endpoints with API key headers
- **Clear Error Handling**: Detailed HTTP error responses for different failure modes

## Architecture

### Layers

- **API Layer** (`app.py`): FastAPI routes with request/response validation
- **Service Layer** (`service.py`): Business logic and domain rules
- **Repository Layer** (`repository.py`): Database access abstraction
- **Models** (`models.py`): SQLAlchemy ORM and Pydantic schemas
- **Security** (`security.py`): API key authentication

### Domain Model

```
SKU
├── available_stock (can be reserved)
└── reserved_stock (held for pending reservations)

Reservation (15-minute TTL)
├── PENDING → can be confirmed or cancelled
├── CONFIRMED → order created, stock committed
├── CANCELLED → released back to available
└── EXPIRED → auto-marked if confirm attempted after TTL

Order
├── PENDING (default status)
├── SHIPPED
└── CANCELLED
```

## Getting Started

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Service

```bash
python -m uvicorn commerce_service.app:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.
API documentation at `http://localhost:8000/docs`.

### Testing

```bash
pytest tests/ -v
```

Run with coverage:
```bash
pytest tests/ --cov=commerce_service --cov-report=html
```

## API Endpoints

### Health Check
```
GET /health
```
Public health check endpoint.

### SKU Management

**Create SKU**
```
POST /skus
Headers: X-API-Key: test-api-key-12345
Body: {
  "sku_id": "SKU001",
  "name": "Product Name",
  "initial_stock": 100
}
```

**Adjust Stock**
```
POST /skus/{sku_id}/adjust-stock
Headers: X-API-Key: test-api-key-12345
Body: {
  "adjustment": 50  # positive or negative
}
```

### Reservations

**Create Reservation**
```
POST /reservations
Headers: X-API-Key: test-api-key-12345
Body: {
  "sku_id": "SKU001",
  "customer_id": "CUST001",
  "quantity": 25,
  "idempotency_key": "optional-unique-key"  # optional
}
```

**Confirm Reservation** (creates order)
```
POST /reservations/{reservation_id}/confirm
Headers: X-API-Key: test-api-key-12345
```

**Cancel Reservation**
```
POST /reservations/{reservation_id}/cancel
Headers: X-API-Key: test-api-key-12345
```

### Orders

**Get Order**
```
GET /orders/{order_id}
```
Public read access.

**List Orders** (paginated)
```
GET /customers/{customer_id}/orders?skip=0&limit=10
```
Public read access. `limit` must be 1-100.

## Key Business Rules

1. **Stock Reservation**: When a reservation is created, stock is immediately reserved and deducted from available inventory.

2. **Reservation TTL**: Reservations automatically expire after 15 minutes. Attempting to confirm an expired reservation returns an error.

3. **Idempotency**: Create reservations with an `idempotency_key` to safely retry. Same key returns the same reservation ID (idempotent operation).

4. **Order Creation**: Only confirmed reservations create orders. Once confirmed, reserved stock is fully committed.

5. **Cancellation**: Pending reservations can be cancelled to release stock back to available inventory.

6. **API Key Protection**: Mutating operations (create, update, delete) require the `X-API-Key` header. Default key: `test-api-key-12345`.

## Error Codes

| Status | Scenario |
|--------|----------|
| 400 | Insufficient stock, expired reservation, invalid request |
| 403 | Missing or invalid API key |
| 404 | SKU, reservation, or order not found |
| 409 | Idempotency key conflict |
| 500 | Internal server error |

## Database

SQLite database stored at `./commerce.db` (created on first run).

Tables:
- `skus`: Product catalog with available and reserved stock
- `reservations`: Hold records with expiration time and status
- `orders`: Confirmed purchases linked to reservations

## Development

### Project Structure

```
src/commerce_service/
├── __init__.py
├── app.py              # FastAPI application
├── models.py           # Pydantic + SQLAlchemy models
├── repository.py       # Database access layer
├── service.py          # Business logic
└── security.py         # Authentication

tests/
├── test_api.py         # Integration tests (FastAPI endpoints)
└── test_service.py     # Unit tests (service layer)

pyproject.toml          # Project metadata and dependencies
README.md               # This file
```

### Adding New Features

1. **New Model**: Add Pydantic schema to `models.py`
2. **New Database Table**: Add SQLAlchemy model to `models.py`
3. **New Repository Method**: Add to `Repository` class in `repository.py`
4. **New Business Logic**: Add to `CommerceService` in `service.py`
5. **New Endpoint**: Add route to `app.py`
6. **Test Coverage**: Add tests to `tests/` matching the feature

### Running Specific Tests

```bash
# Test only service layer
pytest tests/test_service.py -v

# Test only API endpoints
pytest tests/test_api.py -v

# Test a specific class
pytest tests/test_api.py::TestReservationEndpoints -v

# Test a specific function
pytest tests/test_api.py::TestReservationEndpoints::test_create_reservation_happy_path -v
```

## License

Proprietary
