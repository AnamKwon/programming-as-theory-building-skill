# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU and stock management
- Reservation creation with idempotency
- Automatic reservation expiration (15 minutes)
- Order confirmation and cancellation
- API-key authentication for mutations
- Pagination for order lookup

## Quick Start

### Install dependencies

```bash
pip install -e ".[dev]"
```

### Run the server

```bash
python -m uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Run tests

```bash
pytest
```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### SKU Management
- `POST /skus` - Create a new SKU (requires API key)
- `POST /skus/{sku}/adjust-stock` - Adjust stock quantity (requires API key)

### Reservations
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (requires API key)

### Orders
- `GET /orders` - List orders (paginated, requires API key)
- `GET /orders/{order_id}` - Get order details (requires API key)

## Authentication

Provide an `X-API-Key` header for all mutation endpoints:

```bash
curl -H "X-API-Key: secret-key" http://localhost:8000/skus
```

## Architecture

- **models.py**: Pydantic request/response schemas and SQLAlchemy ORM models
- **repository.py**: Data access layer with database queries
- **service.py**: Business logic for reservations, orders, and stock management
- **security.py**: API key validation
- **app.py**: FastAPI application and endpoint definitions

## Design Notes

The service enforces several key invariants:
- Reservations expire after 15 minutes if not confirmed
- Stock is reserved (not deducted) until order confirmation
- Idempotency keys prevent duplicate reservations
- API-key authentication protects state mutations
