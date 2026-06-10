# Commerce Inventory & Order API

A FastAPI-based inventory management and order processing service with reservation and stock management capabilities.

## Features

- **SKU Management**: Create and manage product stock levels
- **Stock Adjustment**: Increase or decrease stock for a given SKU
- **Reservations**: Reserve stock with idempotency guarantees
- **Reservation Lifecycle**: Confirm or cancel reservations with automatic order creation
- **Expiration Handling**: Reservations expire after 300 seconds if not confirmed
- **Order Tracking**: Paginated order retrieval
- **API Key Authentication**: Secure mutation endpoints

## Quick Start

### Install

```bash
pip install -e .
```

### Run

```bash
uvicorn commerce_service.app:app --reload
```

### Test

```bash
pytest tests/
```

## API Endpoints

### Health Check
- `GET /health` - Service health status (no auth required)

### SKU Management
- `POST /skus` - Create a new SKU with initial stock (requires API key)
- `POST /stock/adjust` - Adjust stock level for a SKU (requires API key)

### Reservations
- `POST /reservations` - Create a reservation with idempotency (requires API key)
- `POST /reservations/{id}/confirm` - Confirm a reservation and create an order (requires API key)
- `POST /reservations/{id}/cancel` - Cancel a reservation and restore stock (requires API key)

### Orders
- `GET /orders` - List orders with pagination (no auth required)

## Authentication

All mutation endpoints require a valid API key via the `X-API-Key` header.

Default test API key: `test-api-key-12345`
