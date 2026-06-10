# Commerce Inventory & Order API

A FastAPI-based inventory management and order processing system with stock reservation, confirmation, and order tracking.

## Features

- **SKU Management**: Create and manage stock keeping units with inventory tracking
- **Stock Adjustment**: Adjust stock levels for inventory corrections
- **Reservation System**: Reserve stock with idempotency guarantees
- **Automatic Expiration**: Reservations expire after 300 seconds if not confirmed
- **Order Tracking**: Confirmed reservations create orders with pagination support
- **API Authentication**: Static API key validation for all mutating operations

## Setup

1. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

2. Run the development server:
   ```bash
   uvicorn src.commerce_service.app:app --reload
   ```

3. The API will be available at `http://localhost:8000`

## API Endpoints

### Health Check
```
GET /health
```
Returns: `{"status": "ok"}`

### Create SKU
```
POST /skus
Header: X-API-Key: test-api-key-12345
Body: {"sku": "SKU001", "initial_stock": 100}
```
Response: `201 Created`

### Adjust Stock
```
POST /stock/adjust
Header: X-API-Key: test-api-key-12345
Body: {"sku": "SKU001", "amount": -10}
```
Response: `200 OK`

### Create Reservation
```
POST /reservations
Header: X-API-Key: test-api-key-12345
Body: {"sku": "SKU001", "quantity": 50, "idempotency_key": "unique-key"}
```
Response: `201 Created` or `200 OK` (if idempotent key exists)

### Confirm Reservation
```
POST /reservations/{id}/confirm
Header: X-API-Key: test-api-key-12345
```
Response: `200 OK` (creates an order)

### Cancel Reservation
```
POST /reservations/{id}/cancel
Header: X-API-Key: test-api-key-12345
```
Response: `200 OK`

### Get Orders
```
GET /orders?page=1&size=10
```
Response: `200 OK` with paginated order list

## Testing

Run tests with:
```bash
pytest tests/
```

## Architecture

- **app.py**: FastAPI application and endpoint definitions
- **models.py**: Pydantic request/response models
- **service.py**: Business logic layer
- **repository.py**: Database access layer
- **security.py**: Authentication dependencies
