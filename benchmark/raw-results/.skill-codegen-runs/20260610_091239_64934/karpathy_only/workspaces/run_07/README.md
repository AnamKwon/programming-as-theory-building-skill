# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, SQLAlchemy, and SQLite.

## Features

- **SKU Management**: Create and manage stock-keeping units with real-time inventory tracking
- **Reservations**: Temporary inventory holds with automatic expiration after 10 minutes
- **Idempotency**: Safe retry semantics for reservation creation via idempotency keys
- **Orders**: Confirmed reservations create orders with full state tracking
- **API Key Security**: Required for all mutations, optional for reads
- **Pagination**: Efficient order lookup with configurable page size (1-100)
- **Stock Validation**: Prevents over-reservation and tracks reserved vs available stock

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Server

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

The server starts on `http://localhost:8000` with API docs at `http://localhost:8000/docs`.

### Running Tests

```bash
pytest
```

## API Endpoints

All mutation endpoints require the `X-API-Key: sk-commerce-test-key-123` header.

### Health Check
- **GET /health** — Service readiness check

### SKU Management
- **POST /skus** — Create a new SKU
  ```json
  {
    "code": "PROD-001",
    "quantity_available": 100
  }
  ```

- **PATCH /skus/{sku_id}/stock** — Adjust stock level
  ```json
  {
    "adjustment": -5
  }
  ```

### Reservations
- **POST /reservations** — Create a reservation (10-minute TTL, idempotent)
  ```json
  {
    "sku_id": 1,
    "quantity": 10,
    "idempotency_key": "order-abc-123"
  }
  ```

- **POST /reservations/{reservation_id}/confirm** — Confirm and convert to order

- **DELETE /reservations/{reservation_id}** — Cancel reservation (returns stock)

### Orders
- **GET /orders** — List orders with pagination
  ```
  GET /orders?page=1&page_size=10
  ```

## Design Decisions

### Repository Pattern
Data access is abstracted behind a `Repository` class, enabling easy testing and potential database migration without changing service logic.

### Service Layer
Business rules (stock availability, idempotency, expiration checks) are isolated in `CommercService`, keeping HTTP endpoints thin and testable.

### Idempotency
Reservation creation uses idempotency keys to safely handle retries. A repeated request with the same key returns the original reservation, preventing duplicate stock deductions.

### TTL & Expiration
Reservations expire after 10 minutes. The service validates expiration at confirmation time and marks expired reservations accordingly. Note: Background cleanup (e.g., async task) is not included in this version.

### API Key Security
Hardcoded for testing; replace with proper credential management (env vars, secrets manager) in production. Only mutation endpoints require authentication; read endpoints (health, orders) are public.

## Project Structure

```
.
├── pyproject.toml                 # Dependencies and metadata
├── README.md                      # This file
├── src/commerce_service/
│   ├── __init__.py               # Package marker
│   ├── app.py                    # FastAPI application and endpoints
│   ├── models.py                 # Pydantic and SQLAlchemy models
│   ├── repository.py             # Data access layer
│   ├── service.py                # Business logic
│   └── security.py               # API key validation
└── tests/
    ├── test_service.py           # Service layer unit tests
    └── test_api.py               # API integration tests
```

## Database

SQLite database is automatically created as `commerce.db` on first run. The schema includes:
- `skus` — Stock-keeping units
- `reservations` — Temporary inventory holds
- `orders` — Confirmed purchases

## Testing

The test suite covers:
- SKU creation and stock adjustment
- Reservation creation with stock validation
- Idempotent retry semantics
- Expired reservation rejection
- Unauthorized mutations (missing/invalid API key)
- Pagination edge cases

Run with `pytest -v` for detailed output.

## Production Considerations

For production deployment, consider:
1. **Credential Management**: Move API keys to environment variables or a secrets manager
2. **Database**: Migrate to PostgreSQL for scalability
3. **Monitoring**: Add logging, metrics, and health checks
4. **Async Cleanup**: Implement background tasks for reservation expiration cleanup
5. **Caching**: Add Redis for frequently accessed SKUs
6. **Rate Limiting**: Implement per-API-key quotas
7. **Database Migrations**: Use Alembic for schema versioning
8. **Transactions**: Review isolation levels for concurrent reservation scenarios
