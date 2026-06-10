# Commerce Inventory & Order API

A FastAPI-based service for managing SKU inventory, reservations, and orders with built-in idempotency and reservation expiration handling.

## Features

- **SKU Management**: Create and manage product stock levels
- **Reservations**: Reserve inventory with automatic expiration after 300 seconds
- **Idempotency**: Duplicate reservation requests return the same response without double-deducting stock
- **Orders**: Convert confirmed reservations into orders with pagination support
- **Authentication**: API token validation for all mutating endpoints

## Technical Stack

- **Framework**: FastAPI
- **Validation**: Pydantic v2
- **Database**: SQLite3
- **Testing**: pytest

## Installation

```bash
pip install -e ".[dev]"
```

## Running the Server

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

## Running Tests

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Returns `{"status": "ok"}`

### SKU Management
- `POST /skus` - Create a new SKU with initial stock

### Stock Adjustment
- `POST /stock/adjust` - Adjust stock levels for a SKU

### Reservations
- `POST /reservations` - Create a new reservation
- `POST /reservations/{id}/confirm` - Confirm a pending reservation
- `POST /reservations/{id}/cancel` - Cancel a pending reservation

### Orders
- `GET /orders` - List orders with pagination (page, size parameters)

## Environment

Set `API_TOKEN` environment variable for authentication (default: "test-token").
