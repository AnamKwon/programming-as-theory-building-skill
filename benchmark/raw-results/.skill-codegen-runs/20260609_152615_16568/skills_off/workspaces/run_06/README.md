# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Inventory Reservation**: Reserve stock with idempotency guarantees
- **Order Orchestration**: Confirm or cancel reservations with automatic order creation
- **Stock Adjustment**: Increase or decrease inventory levels
- **API Security**: API-key-based authentication for mutations
- **Pagination**: Efficient order lookup with pagination support

## Quick Start

### Install dependencies

```bash
pip install -e ".[dev]"
```

### Run the service

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Run tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health
- `GET /health` - Service health check

### SKUs
- `POST /skus` - Create a new SKU
- `POST /skus/{sku_id}/stock` - Adjust stock quantity

### Reservations
- `POST /reservations` - Create a reservation (reserves stock)
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation (creates order)
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation (releases stock)

### Orders
- `GET /orders` - List orders with pagination

## Authentication

Mutating endpoints require an `X-API-Key` header:

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"sku": "PROD-001", "stock_qty": 100}'
```

## Design

- **Service Layer**: Business logic and invariant enforcement
- **Repository Pattern**: Abstracted database access
- **Pydantic Models**: Request/response validation
- **SQLite**: Lightweight persistence
- **Idempotency**: Reservation creation is idempotent via idempotency keys
