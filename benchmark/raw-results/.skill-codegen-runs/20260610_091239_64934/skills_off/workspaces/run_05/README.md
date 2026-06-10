# Commerce Service

A production-style inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage product SKUs with stock tracking
- **Inventory Reservations**: Reserve inventory with automatic expiration
- **Idempotency**: Prevent duplicate reservations using idempotency keys
- **Order Orchestration**: Confirm reservations into orders with state tracking
- **Stock Availability**: Real-time stock availability calculation accounting for pending and confirmed reservations
- **API Key Security**: Protect mutating endpoints with API key authentication
- **Pagination**: List orders with offset/limit pagination
- **Clear HTTP Errors**: Structured error responses with appropriate status codes

## Architecture

```
app.py           - FastAPI routes and HTTP handlers
├── security.py  - API key validation
├── service.py   - Business logic and orchestration
├── repository.py - Database access layer
└── models.py    - Pydantic schemas and SQLAlchemy ORM
```

### Design Principles

- **Repository Pattern**: Database access isolated in repository layer
- **Service Layer**: All business rules enforced in the service, not in routes
- **Validation**: Pydantic handles request validation; service enforces domain rules
- **Error Handling**: Clear exception types map to HTTP status codes

## API Endpoints

### Health

- `GET /health` - Health check

### SKUs

- `POST /skus` - Create a SKU (requires API key)
- `GET /skus/{sku_code}` - Get SKU details including stock and reserved quantities
- `PATCH /skus/{sku_code}/stock` - Adjust stock by delta amount (requires API key)

### Reservations

- `POST /reservations` - Create a reservation (requires API key)
  - Returns 409 if insufficient stock
  - Returns 410 if idempotent key has expired
  - Idempotent: same key always returns same reservation
- `POST /reservations/{reservation_id}/confirm` - Confirm a pending reservation (requires API key)
  - Creates an order when confirmed
  - Returns 410 if reservation has expired
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders

- `GET /orders` - List orders with pagination (query params: offset, limit)

## Installation

```bash
pip install -e .
```

Or with dev dependencies:

```bash
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`. OpenAPI docs at `/docs`.

## Testing

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=commerce_service tests/
```

## Configuration

### API Key

The default API key is `commerce-service-key`. Set via the `verify_api_key` function in `security.py`.

### Reservation TTL

Default reservation TTL is 15 minutes. Configure via `CommercService.RESERVATION_TTL_MINUTES`.

### Database

Default database is SQLite at `./commerce.db`. Override the database URL in `app.py`:

```python
engine = get_engine("postgresql://user:password@localhost/commerce")
```

## Request Examples

### Create SKU

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: commerce-service-key" \
  -H "Content-Type: application/json" \
  -d '{"sku": "WIDGET-001", "name": "Widget A", "stock": 100}'
```

### Create Reservation

```bash
curl -X POST http://localhost:8000/reservations \
  -H "X-API-Key: commerce-service-key" \
  -H "Content-Type: application/json" \
  -d '{
    "sku": "WIDGET-001",
    "quantity": 10,
    "idempotency_key": "order-12345"
  }'
```

### Confirm Reservation

```bash
curl -X POST http://localhost:8000/reservations/1/confirm \
  -H "X-API-Key: commerce-service-key" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### List Orders

```bash
curl http://localhost:8000/orders?offset=0&limit=50
```

## Service Rules

1. **Stock Availability**: Accounts for both pending and confirmed reservations
2. **Reservation Expiration**: Pending reservations automatically expire after 15 minutes
3. **Idempotency**: Same idempotency key always returns the same reservation ID
4. **State Transitions**:
   - `PENDING` → `CONFIRMED` (on confirm)
   - `PENDING` → `CANCELLED` (on cancel)
   - `PENDING` → `EXPIRED` (after TTL)
   - `CONFIRMED` → `CANCELLED` (on cancel)
5. **Order Creation**: Orders created only when reservations are confirmed

## HTTP Status Codes

- `200 OK` - Successful GET
- `201 Created` - Successful POST (resource created)
- `400 Bad Request` - Invalid request payload
- `401 Unauthorized` - Invalid API key
- `404 Not Found` - Resource not found
- `409 Conflict` - Insufficient stock, duplicate SKU, invalid state transition
- `410 Gone` - Reservation expired
- `422 Unprocessable Entity` - Validation error

## Development

### Adding a New Endpoint

1. Define request/response schemas in `models.py`
2. Add business logic to `CommercService` in `service.py`
3. Add route handler in `app.py`
4. Add tests to `tests/test_api.py` and `tests/test_service.py`

### Database Schema

Run migrations to update schema:

```python
from commerce_service.models import init_db, get_engine
init_db(get_engine())
```

## License

MIT
