# Commerce Inventory & Order API

A FastAPI-based REST API for managing inventory, reservations, and orders with stock management and idempotent reservation handling.

## Features

- **SKU Management**: Create and track product inventory
- **Stock Adjustment**: Increase or decrease stock levels
- **Reservations**: Reserve inventory with idempotent key support
- **Expiration**: Automatically expire reservations older than 300 seconds
- **Orders**: Confirm reservations to create orders
- **Pagination**: List orders with configurable pagination
- **Security**: API token-based authentication for mutations

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Application

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.
API documentation: `http://localhost:8000/docs`

## Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` - Check API status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires auth)
- `POST /stock/adjust` - Adjust stock levels (requires auth)

### Reservations
- `POST /reservations` - Create a reservation (requires auth)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation (requires auth)
- `POST /reservations/{id}/cancel` - Cancel a pending reservation (requires auth)

### Orders
- `GET /orders` - List orders with pagination (requires auth)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an API token via the `X-API-Key` header.

Default test token: `test-api-key-12345`
