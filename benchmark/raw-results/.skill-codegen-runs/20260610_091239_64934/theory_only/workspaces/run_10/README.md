# Commerce Service

Inventory reservation and order orchestration API for e-commerce backends.

## Features

- Inventory management with SKUs and stock levels
- Reservation system with automatic expiration
- Order creation and confirmation with state tracking
- Idempotent operations via idempotency keys
- API-key authentication for mutations
- Paginated order lookup
- SQLite persistence

## Getting Started

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the Service

```bash
commerce-service
# or
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest tests/
pytest tests/ -v  # verbose output
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a SKU with initial stock
- `POST /skus/{sku_id}/adjust` - Adjust stock level

### Reservations
- `POST /reservations` - Create a reservation for a SKU
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (converts to order)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination
- `GET /orders/{order_id}` - Get order details

## API Key

Use the `X-API-Key` header for mutating endpoints. Default: `dev-key-001`.

## Architecture

- **models.py** - Pydantic request/response models and SQLAlchemy ORM entities
- **repository.py** - Database access layer (SQLAlchemy)
- **service.py** - Business logic and validation
- **security.py** - Authentication and authorization
- **app.py** - FastAPI application and endpoint definitions
