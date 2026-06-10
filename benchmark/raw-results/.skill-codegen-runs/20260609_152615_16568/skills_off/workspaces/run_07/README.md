# Commerce Service

A production-ready inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage product SKUs with inventory tracking.
- **Stock Control**: Adjust inventory levels with delta updates.
- **Reservation System**: Reserve inventory with automatic expiration (15 minutes TTL).
- **Idempotency**: Safe retry semantics via idempotency keys.
- **Order Orchestration**: Confirm reservations into orders with state transitions.
- **API Security**: API key authentication for mutating endpoints.
- **Pagination**: Efficient order lookup with pagination support.

## Architecture

- **Models** (`models.py`): Pydantic schemas for request/response validation.
- **Repository** (`repository.py`): SQLite data access layer with connection pooling.
- **Service** (`service.py`): Business logic for stock allocation, reservation expiration, and order state.
- **Security** (`security.py`): API key validation dependency.
- **App** (`app.py`): FastAPI application with endpoint routing.

## API Endpoints

### Public
- `GET /health` - Health check

### Mutating (Requires `X-API-Key` header)
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock level
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation into an order
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `POST /maintenance/cleanup-expired` - Expire old pending reservations

### Public Read
- `GET /orders/{id}` - Get order details with items
- `GET /customers/{id}/orders` - List orders with pagination
  - Query parameters: `page` (default 1), `page_size` (default 10, max 100)

## Installation

```bash
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --host 0.0.0.0 --port 8000
```

For development with auto-reload:
```bash
uvicorn commerce_service.app:app --host 0.0.0.0 --port 8000 --reload
```

## Testing

```bash
pytest tests/
```

For coverage:
```bash
pytest tests/ --cov=commerce_service
```

## API Key

Default test API keys:
- `test-key-12345`
- `sk_live_production_key`

Set the `X-API-Key` header for mutating requests:
```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"sku": "WIDGET-001", "name": "Premium Widget"}'
```

## Error Handling

- `400 Bad Request` - Invalid request payload or state violation
- `401 Unauthorized` - Missing or invalid API key
- `404 Not Found` - Resource not found
- `409 Conflict` - Insufficient stock
- `410 Gone` - Reservation expired

## Database

SQLite database (`commerce.db`) is auto-initialized on first run with the following schema:

- `skus` - Product definitions
- `stock` - Current inventory levels
- `reservations` - Reservation records with status tracking
- `orders` - Order records

## Design Patterns

### Reservation Lifecycle
1. **Create**: Reserve stock at fixed TTL (15 minutes)
2. **Confirm**: Transition to confirmed and create an order
3. **Cancel**: Release the reservation
4. **Expire**: Auto-expire pending reservations after TTL

### Stock Accounting
- Available stock = total stock - reserved (pending + confirmed)
- Reservations block inventory from other customers
- Confirming a reservation creates an order but doesn't reduce stock

### Idempotency
- All reservation requests use `idempotency_key` for safe retries
- Duplicate keys return the existing reservation with `idempotent: true` flag
- Expired reservations reject idempotent retries with 410 Gone

### API Security
- Mutating endpoints require `X-API-Key` header
- Public read endpoints (orders, health) allow unauthenticated access
- Keys validated against a set of valid keys in `security.py`
