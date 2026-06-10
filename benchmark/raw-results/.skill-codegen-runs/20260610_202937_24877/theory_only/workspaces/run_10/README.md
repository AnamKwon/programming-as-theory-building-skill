# Commerce Inventory & Order API

A FastAPI-based REST API for managing inventory, reservations, and orders with built-in validation, idempotency support, and expiration handling.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Adjust inventory levels with positive or negative amounts
- **Reservations**: Reserve stock with idempotency key support
- **Expiration Handling**: Automatically expire reservations after 300 seconds
- **Order Management**: Confirm reservations to create orders with pagination support
- **API Token Security**: All mutations require valid API token authentication

## Technical Stack

- **Framework**: FastAPI
- **Validation**: Pydantic v2
- **Database**: SQLite (sqlite3)
- **Testing**: pytest

## Installation

```bash
pip install -e .
```

## Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Interactive API docs available at `http://localhost:8000/docs`

## API Endpoints

### Health Check
- `GET /health` - Returns {"status": "ok"}

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires auth)
- `POST /stock/adjust` - Adjust stock level for a SKU (requires auth)

### Reservations
- `POST /reservations` - Create a reservation (requires auth, idempotent)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation (requires auth)
- `POST /reservations/{id}/cancel` - Cancel a pending reservation (requires auth)

### Orders
- `GET /orders` - List orders with pagination (default: page=1, size=10)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an API token via Bearer authentication:

```bash
curl -H "Authorization: Bearer test-api-key-123" http://localhost:8000/skus
```

## Business Rules

### Reservation Creation
1. Stock must be available (available_stock >= quantity requested)
2. Idempotency key ensures duplicate requests return cached result
3. Stock is immediately deducted upon reservation

### Reservation Confirmation
1. Reservation must be in PENDING status
2. Reservation must not be older than 300 seconds
3. If expired, status changes to EXPIRED and stock is restored
4. Successful confirmation creates an Order record

### Reservation Cancellation
1. Reservation must be in PENDING status
2. Reserved stock is immediately restored

## Testing

```bash
pytest tests/
```

## Database

SQLite database file: `commerce.db`

Tables:
- `skus` - SKU inventory with stock levels
- `reservations` - Pending/confirmed/cancelled reservations
- `orders` - Confirmed orders linked to reservations
