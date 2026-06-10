# Commerce Inventory & Order API

A FastAPI-based inventory and order management system with stock reservation, confirmation, and cancellation workflows.

## Features

- SKU management with stock tracking
- Stock adjustments (additions/deductions)
- Idempotent reservation system with 300-second expiration
- Reservation confirmation and cancellation with stock restoration
- Order pagination
- API token authentication for mutating operations
- SQLite persistence with repository pattern

## Quick Start

### Installation

```bash
pip install -e .
```

### Running the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

Server will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest tests/
```

## API Endpoints

### Health Check
- **GET /health** - No authentication required
  ```json
  {"status": "ok"}
  ```

### SKU Management
- **POST /skus** - Create a new SKU
  ```json
  {"sku": "PRODUCT-123", "initial_stock": 100}
  ```

### Stock Adjustment
- **POST /stock/adjust** - Adjust stock levels
  ```json
  {"sku": "PRODUCT-123", "amount": -5}
  ```

### Reservations
- **POST /reservations** - Create a reservation
  ```json
  {"sku": "PRODUCT-123", "quantity": 10, "idempotency_key": "unique-key-123"}
  ```

- **POST /reservations/{id}/confirm** - Confirm a reservation
  Creates an order and finalizes the reservation.

- **POST /reservations/{id}/cancel** - Cancel a reservation
  Restores reserved stock to available inventory.

### Orders
- **GET /orders** - Get paginated orders
  Query parameters: `page` (default: 1), `size` (default: 10)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an API token via the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" -X POST http://localhost:8000/skus \
  -H "Content-Type: application/json" \
  -d '{"sku": "PRODUCT-123", "initial_stock": 100}'
```

Default API key: `test-key-123`

## Environment Variables

- `API_KEY` - API token for authentication (default: "test-key-123")
- `DATABASE_URL` - SQLite database path (default: "sqlite:///./commerce.db")

## Business Rules

1. **Stock Check**: Reservation fails if available stock < requested quantity (HTTP 400)
2. **Idempotency**: Duplicate idempotency keys return previous response without mutating stock
3. **Expiration**: Reservations expire 300 seconds after creation and cannot be confirmed
4. **State Validation**: Confirmations/cancellations require PENDING status
5. **Stock Restoration**: Cancelled/expired reservations restore stock immediately
