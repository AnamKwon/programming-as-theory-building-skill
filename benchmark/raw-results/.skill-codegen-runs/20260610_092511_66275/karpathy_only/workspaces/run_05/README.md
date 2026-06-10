# Commerce Service

A production-ready inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create and manage stock keeping units with stock tracking
- **Reservation System**: Reserve inventory with TTL-based expiration (15 minutes default)
- **Order Fulfillment**: Confirm reservations to create orders
- **Idempotency**: Duplicate requests with the same key return existing results
- **Stock Validation**: Prevent reservations exceeding available stock
- **API Key Security**: Protected mutation endpoints with API key validation
- **Pagination**: Efficient order lookup with limit/offset pagination
- **SQLite Storage**: Self-contained file-based database

## Architecture

```
app.py              → FastAPI application with endpoint definitions
├── service.py     → Business logic and validation rules
├── repository.py  → Database access layer (SQLite)
├── models.py      → Pydantic request/response models
└── security.py    → API key dependency
```

## Getting Started

### Install

```bash
pip install -e ".[dev]"
```

### Run the Service

```bash
uvicorn commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`

### API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

All mutation endpoints require `X-API-Key: test-key-123` header.

### Health Check

```
GET /health
```

### SKU Management

```
POST /skus
  Body: {"sku_code": "SKU-001", "stock_qty": 100}
  
POST /skus/{sku_id}/stock
  Body: {"adjustment": 50}
```

### Reservations

```
POST /reservations
  Body: {
    "sku_code": "SKU-001",
    "qty": 25,
    "idempotency_key": "unique-key-123"
  }
  
POST /reservations/{reservation_id}/confirm
  Body: {"idempotency_key": "unique-key-123"}
  
POST /reservations/{reservation_id}/cancel
```

### Orders

```
GET /orders/{order_id}

GET /orders?limit=20&offset=0
```

## Testing

```bash
pytest tests/ -v
```

### Test Coverage

- SKU creation and duplicate handling
- Stock adjustment (positive/negative/validation)
- Reservation creation with stock validation
- Idempotency key handling for reservations
- Reservation confirmation and order creation
- Expired reservation rejection
- Unauthorized mutation rejection
- Order lookup and pagination

## Data Model

### SKUs
- `id`: Primary key
- `sku_code`: Unique identifier (e.g., "SKU-001")
- `stock_qty`: Current available inventory

### Reservations
- `id`: Primary key
- `sku_id`: Foreign key to SKU
- `qty`: Reserved quantity
- `status`: PENDING, CONFIRMED, or CANCELLED
- `idempotency_key`: Unique request identifier
- `created_at`: Timestamp
- `expires_at`: Reservation expiration (TTL: 15 minutes)

### Orders
- `id`: Primary key
- `reservation_id`: Foreign key to reservation
- `sku_id`: Foreign key to SKU
- `qty`: Order quantity
- `status`: CREATED or FULFILLED
- `created_at`: Timestamp

## Security

- API key validation on all mutation endpoints
- Idempotency keys prevent duplicate order creation
- Stock validation prevents overselling
- Reservation TTL prevents indefinite holds

## Production Considerations

- Replace hardcoded API keys with environment variables
- Implement database connection pooling for high concurrency
- Add request logging and monitoring
- Implement distributed locking for high-traffic scenarios
- Add comprehensive error tracking (Sentry, etc.)
- Use a production ASGI server (Gunicorn + Uvicorn)
- Add rate limiting and request validation
- Implement database backup strategy

## Development

Run tests with coverage:

```bash
pytest tests/ --cov=commerce_service --cov-report=html
```

Type checking:

```bash
# Install mypy and run
mypy src/
```
