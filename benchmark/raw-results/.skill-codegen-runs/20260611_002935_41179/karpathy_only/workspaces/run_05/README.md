# Commerce Inventory & Order API

A FastAPI-based service for managing inventory, reservations, and orders with strict stock controls and idempotency guarantees.

## Setup

```bash
pip install -e ".[test]"
```

## Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## API Token

All mutating endpoints require an API token passed via the `X-API-Key` header. Default token: `test-key-123`

## Core Features

- **SKU Management**: Create and manage stock-keeping units
- **Stock Adjustment**: Modify inventory levels
- **Reservations**: Reserve stock with idempotency guarantees
- **Expiration**: Reservations expire after 300 seconds
- **Orders**: Confirm reservations and create orders with pagination

## Running Tests

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock level
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (paginated)
