# Commerce Inventory & Order API

A FastAPI-based inventory and order management system with SKU management, stock adjustments, reservation handling, and order tracking.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustments**: Increase or decrease available stock
- **Reservations**: Reserve inventory with idempotency support
- **Expiration Handling**: Automatic expiration of reservations older than 300 seconds
- **Order Management**: Convert confirmed reservations into orders with pagination
- **API Token Authentication**: Secure mutating operations with static API token validation

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Running the Server

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`

### Running Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` - Returns service status (no authentication required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API token)
- `POST /stock/adjust` - Adjust stock level for a SKU (requires API token)

### Reservations
- `POST /reservations` - Create a stock reservation with idempotency (requires API token)
- `POST /reservations/{id}/confirm` - Confirm a pending reservation and create an order (requires API token)
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock (requires API token)

### Orders
- `GET /orders` - List orders with pagination (no authentication required)

## Authentication

All mutating endpoints (POST, PUT, DELETE) require an `X-API-Key` header with a valid API token.

Default token: `test-token-12345`

## Database

Uses SQLite with three main tables:
- `skus` - Product SKU information and stock levels
- `reservations` - Stock reservations with status and idempotency tracking
- `orders` - Confirmed orders linked to reservations
