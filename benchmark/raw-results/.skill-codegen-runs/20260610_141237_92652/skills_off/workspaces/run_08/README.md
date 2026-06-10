# Commerce Inventory & Order API

A FastAPI-based service for managing SKU inventory, reservations, and orders.

## Features

- **SKU Management**: Register SKUs with initial stock levels
- **Stock Adjustment**: Adjust inventory levels up or down
- **Reservation System**: Reserve inventory with idempotency and expiration checks
- **Order Creation**: Convert confirmed reservations into orders
- **Pagination**: Browse orders with configurable page size

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Run the Server

```bash
uvicorn src.commerce_service.app:app --reload
```

### Run Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### Inventory Management
- `POST /skus` - Register a new SKU
- `POST /stock/adjust` - Adjust stock levels

### Reservations
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation

### Orders
- `GET /orders` - List orders with pagination

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an API token in the `X-API-Key` header.

Default token for testing: `test-api-key`

## Database

SQLite database is automatically initialized on first run as `commerce.db`.
