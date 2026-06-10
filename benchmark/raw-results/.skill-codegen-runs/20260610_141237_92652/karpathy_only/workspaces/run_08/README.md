# Commerce Inventory & Order API

A FastAPI-based inventory and order management service with stock reservation, confirmation, and cancellation workflows.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Increase or decrease available stock
- **Reservations**: Reserve inventory with idempotency guarantees
- **Confirmation & Cancellation**: Manage reservation lifecycle with expiration enforcement
- **Order Tracking**: Paginated order listing
- **API Token Security**: Secure all mutating operations with token validation

## Requirements

- Python 3.9+
- FastAPI 0.100+
- SQLAlchemy 2.0+
- Pydantic 2.0+

## Installation

```bash
pip install -e .[dev]
```

## Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` - Service health check (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API token)
- `POST /stock/adjust` - Adjust stock level for a SKU (requires API token)

### Reservations
- `POST /reservations` - Create a stock reservation (requires API token)
- `POST /reservations/{id}/confirm` - Confirm a reservation and create an order (requires API token)
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock (requires API token)

### Orders
- `GET /orders` - List orders with pagination (no authentication required)

## API Token

All mutating endpoints (POST, PUT, DELETE) require an API token via the `X-API-Token` header.

Default token: `test-token-123`

Example:
```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Token: test-token-123" \
  -H "Content-Type: application/json" \
  -d '{"sku": "PROD-001", "initial_stock": 100}'
```

## Database

The service uses SQLite for data persistence. The database file is created automatically at `commerce.db`.

## Business Rules

- **Stock Availability**: Reservations fail if insufficient stock is available
- **Idempotency**: Identical reservation requests return the same result without duplicating deductions
- **Expiration**: Reservations expire 300 seconds after creation and cannot be confirmed
- **State Validation**: Only PENDING reservations can be confirmed or cancelled
- **Stock Restoration**: Cancelled reservations restore their quantity to available stock
