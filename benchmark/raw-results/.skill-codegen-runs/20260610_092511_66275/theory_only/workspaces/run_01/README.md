# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage product SKUs
- **Stock Tracking**: Track available and reserved inventory
- **Reservations**: Temporary holds on inventory with TTL-based expiration
- **Order Orchestration**: Convert reservations into confirmed orders
- **Idempotency**: Duplicate request detection via idempotency keys
- **API Security**: API key validation for mutating endpoints
- **Pagination**: Cursor-free offset/limit pagination for order listing

## Architecture

### Layers

- **API Layer** (`app.py`): FastAPI HTTP endpoints and request validation
- **Service Layer** (`service.py`): Business logic for reservations, orders, and inventory rules
- **Repository Layer** (`repository.py`): Data access abstractions
- **Models** (`models.py`): Pydantic request/response schemas and SQLAlchemy ORM models
- **Security** (`security.py`): API key validation

### Domain Model

**Stock Flow**:
1. Create SKU and initialize stock
2. Adjust stock quantity (purchase, return, loss)
3. Create reservation (decrements available quantity)
4. Confirm reservation (converts to order, decrements physical quantity)
5. Cancel reservation (releases hold, increments available)

**Reservation Lifecycle**:
- `pending`: Created, awaiting confirmation
- `confirmed`: Converted to an order
- `cancelled`: Explicitly cancelled
- `expired`: TTL exceeded, automatically released

**Order States**:
- `confirmed`: Active order created from reservation confirmation

## Installation

```bash
pip install -e ".[dev]"
```

## Running

### Development Server

```bash
uvicorn commerce_service.app:app --reload
```

Server listens on `http://localhost:8000`

### Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health

```
GET /health
```
Returns `{"status": "ok"}`.

### SKU Management

```
POST /skus
X-API-Key: <key>
Content-Type: application/json

{
  "id": "SKU-001",
  "name": "Widget"
}
```
Returns `201 Created` with SKU details.

### Stock Adjustment

```
POST /stock/adjust
X-API-Key: <key>
Content-Type: application/json

{
  "sku_id": "SKU-001",
  "delta": 100
}
```
Positive `delta` adds stock, negative removes. Returns current stock state.

### Reservations

**Create**:
```
POST /reservations
X-API-Key: <key>
Content-Type: application/json

{
  "sku_id": "SKU-001",
  "quantity": 50,
  "idempotency_key": "optional-key",
  "ttl_seconds": 300
}
```
Returns `201 Created` with reservation details. Fails with `400` if insufficient stock.

**Confirm**:
```
POST /reservations/{reservation_id}/confirm
X-API-Key: <key>
```
Creates an order and releases the hold from stock. Returns order details.

**Cancel**:
```
POST /reservations/{reservation_id}/cancel
X-API-Key: <key>
```
Releases the hold and marks reservation as cancelled. Returns cancellation confirmation.

### Orders

**Get by ID**:
```
GET /orders/{order_id}
```
Returns order details.

**List with Pagination**:
```
GET /orders?offset=0&limit=20
```
Returns paginated order list with total count.

## API Keys

For testing, valid keys are:
- `test-key-1`
- `test-key-2`

Pass via `X-API-Key` header.

## Key Design Decisions

1. **Separation of Concerns**: Repository handles persistence, service handles rules, API handles HTTP.
2. **No Over-Engineering**: Idempotency via simple unique constraint on idempotency keys.
3. **Stock Tracking**: Separate `quantity` (physical) and `reserved` (held) fields.
4. **TTL-Based Expiration**: Reservations expire after specified seconds; cleanup occurs on demand.
5. **Stateless API**: No sessions or state tracking beyond database.
6. **SQLite**: Sufficient for small commerce backend; easily upgradeable to PostgreSQL.

## Testing

### Test Coverage

- Happy paths: SKU creation, reservation → confirmation → order
- Edge cases: Insufficient stock, idempotent retry, expired reservations
- Validation: Unauthorized mutations, invalid inputs
- Pagination: Offset/limit bounds, empty result sets

### Running Tests

```bash
pytest tests/ -v --tb=short
```

### Test Database

Tests use temporary SQLite databases that are cleaned up after each test. No test data persists.

## Error Responses

All HTTP errors follow this format:

```json
{
  "detail": "Human-readable error message",
  "code": "error"
}
```

Common status codes:
- `400 Bad Request`: Invalid input or business logic violation (insufficient stock, expired reservation)
- `401 Unauthorized`: Missing or invalid API key
- `404 Not Found`: Resource not found
- `409 Conflict`: Duplicate SKU

## Development

### Project Structure

```
.
├── pyproject.toml
├── README.md
├── src/commerce_service/
│   ├── __init__.py
│   ├── app.py           # FastAPI application
│   ├── models.py        # Pydantic + SQLAlchemy models
│   ├── repository.py    # Data access layer
│   ├── service.py       # Business logic
│   └── security.py      # API key validation
└── tests/
    ├── __init__.py
    ├── test_api.py      # HTTP endpoint tests
    └── test_service.py  # Service layer tests
```

### Adding Endpoints

1. Add request/response models to `models.py`
2. Implement business logic in `service.py`
3. Add HTTP endpoint in `app.py`
4. Add tests in `tests/test_api.py`

### Database Migrations

Currently uses SQLAlchemy's declarative models. For production, consider:
- Alembic for schema versioning
- Separate migration scripts for deployment

## Production Considerations

1. **Database**: Upgrade to PostgreSQL for concurrency and reliability
2. **Authentication**: Replace API key with OAuth 2.0 or similar
3. **Logging**: Add structured logging (e.g., JSON logs to CloudWatch)
4. **Monitoring**: Add APM (e.g., Datadog, New Relic) and alerting
5. **Caching**: Add Redis for reservation state and stock reads
6. **Rate Limiting**: Implement rate limiting per API key
7. **Async Cleanup**: Move expired reservation cleanup to background job
8. **Transactions**: Add explicit transaction boundaries for multi-step operations
