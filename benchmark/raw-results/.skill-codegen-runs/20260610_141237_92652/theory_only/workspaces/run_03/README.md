# Commerce Inventory & Order API

A FastAPI-based inventory and order management service with support for SKU creation, stock management, reservation handling, and order fulfillment.

## Features

- **SKU Management**: Create and manage product SKUs with stock tracking
- **Stock Adjustment**: Adjust inventory levels dynamically
- **Reservations**: Reserve inventory with idempotency and expiration checks
- **Order Fulfillment**: Confirm reservations to create orders
- **API Authentication**: Token-based authentication for mutations
- **Pagination**: Paginated order listing

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn commerce_service.app:app --reload
```

## Running Tests

```bash
pytest tests/
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create SKU
- `POST /stock/adjust` - Adjust stock levels
- `POST /reservations` - Create reservation
- `POST /reservations/{id}/confirm` - Confirm reservation
- `POST /reservations/{id}/cancel` - Cancel reservation
- `GET /orders` - List orders (paginated)

## Authentication

Mutating endpoints require an `X-API-Key` header with a valid API token.
