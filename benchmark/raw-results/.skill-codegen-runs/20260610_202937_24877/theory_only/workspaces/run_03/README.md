# Commerce Inventory & Order API

A FastAPI-based REST API for managing inventory SKUs, stock adjustments, reservations, and orders with comprehensive validation and business logic enforcement.

## Features

- **SKU Management**: Create and manage product SKUs with stock tracking
- **Stock Adjustments**: Adjust stock levels with positive or negative amounts
- **Reservations**: Reserve inventory with idempotent request handling
- **Reservation Lifecycle**: Confirm or cancel pending reservations
- **Order Management**: Automatically create orders when reservations are confirmed
- **Expiration Handling**: Prevent confirmation of reservations older than 300 seconds
- **API Authentication**: Token-based authentication for all mutating endpoints
- **Pagination**: Paginated order listing with configurable page size

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` - Check API health status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock
  - Required: `X-API-Key` header
  - Body: `{"sku": "string", "initial_stock": int}`

- `POST /stock/adjust` - Adjust stock for a SKU
  - Required: `X-API-Key` header
  - Body: `{"sku": "string", "amount": int}`

### Reservations
- `POST /reservations` - Create a reservation
  - Required: `X-API-Key` header
  - Body: `{"sku": "string", "quantity": int, "idempotency_key": "string"}`
  - Returns: 201 Created on success, 400 on insufficient stock

- `POST /reservations/{id}/confirm` - Confirm a pending reservation
  - Required: `X-API-Key` header
  - Returns: 200 OK with created order, 400 if expired or not pending

- `POST /reservations/{id}/cancel` - Cancel a pending reservation
  - Required: `X-API-Key` header
  - Returns: 200 OK with updated reservation

### Orders
- `GET /orders` - List orders with pagination
  - Query params: `page` (default: 1), `size` (default: 10)
  - No authentication required

## Business Rules

1. **Stock Validation**: Reservations are rejected if requested quantity exceeds available stock
2. **Idempotency**: Identical idempotency keys return the previous response without modifying inventory
3. **Expiration**: Reservations cannot be confirmed if created more than 300 seconds ago
4. **State Transitions**: Only pending reservations can be confirmed or cancelled
5. **Stock Restoration**: Cancelled reservations and expired confirmation attempts restore stock

## Testing

The project includes comprehensive tests covering:
- Happy path workflow (SKU → Reserve → Confirm → Order lookup)
- Stock insufficiency validation
- Idempotent retry behavior
- Expiration detection and stock restoration
- API authentication and authorization
- Pagination functionality

Run tests with:
```bash
pytest tests/ -v
```

## Database

The API uses SQLite with three main tables:
- `skus`: Product SKUs and their stock levels
- `reservations`: Reserved inventory with status tracking
- `orders`: Confirmed orders

The database is automatically initialized on server startup.

## Configuration

Default API Key: `test-api-key-12345`

Modify `security.py` to change the valid API key for your environment.
