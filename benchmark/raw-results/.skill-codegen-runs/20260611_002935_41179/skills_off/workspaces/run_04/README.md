# Commerce Inventory & Order API

A FastAPI-based service for managing inventory, reservations, and orders.

## Features

- SKU management with stock levels
- Reservation system with idempotency
- Order confirmation workflow
- Stock adjustment API
- Pagination support

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the API

```bash
uvicorn commerce_service.app:app --reload
```

### Running Tests

```bash
pytest
```

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a new SKU with initial stock (requires API key)
- `POST /stock/adjust` - Adjust stock levels (requires API key)
- `POST /reservations` - Create a reservation (requires API key)
- `POST /reservations/{id}/confirm` - Confirm a reservation (requires API key)
- `POST /reservations/{id}/cancel` - Cancel a reservation (requires API key)
- `GET /orders` - List orders (paginated, requires API key)

## Authentication

All mutating endpoints (POST, PUT, DELETE) and GET /orders require an API key via the `X-API-Key` header.
