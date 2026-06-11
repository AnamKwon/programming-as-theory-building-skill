# Commerce Inventory & Order API

A FastAPI-based REST API for managing SKU inventory, reservations, and orders with stock management and idempotent operations.

## Features

- **SKU Management**: Create and manage product SKUs with stock levels
- **Stock Adjustment**: Adjust inventory levels (increase/decrease)
- **Reservations**: Create time-limited reservations with idempotent key support
- **Order Confirmation**: Confirm reservations and create orders with automatic expiration
- **Pagination**: Browse orders with configurable page size
- **API Security**: Token-based authentication for all mutating operations

## Quick Start

### Install Dependencies

```bash
pip install -e .
```

### Run the API

```bash
python -m uvicorn commerce_service.app:app --reload
```

### Run Tests

```bash
pytest
```

## API Endpoints

- `GET /health` - Health check (no auth required)
- `POST /skus` - Create a new SKU (requires API token)
- `POST /stock/adjust` - Adjust stock for a SKU (requires API token)
- `POST /reservations` - Create a reservation (requires API token)
- `POST /reservations/{id}/confirm` - Confirm a reservation (requires API token)
- `POST /reservations/{id}/cancel` - Cancel a reservation (requires API token)
- `GET /orders` - List orders with pagination (no auth required)

## Authentication

Pass the API token via the `X-API-Key` header for all mutating operations:

```bash
curl -H "X-API-Key: test-api-key" POST /skus ...
```
