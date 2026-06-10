# Commerce Inventory & Order API

A FastAPI-based service for managing SKU inventory, reservations, and orders with idempotent reservation handling and time-based expiration.

## Quick Start

### Installation
```bash
pip install -e ".[dev]"
```

### Running the Server
```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

Health check: `curl http://localhost:8000/health`

### Running Tests
```bash
pytest tests/ -v
```

## API Endpoints

- **GET /health** - Health check (no auth)
- **POST /skus** - Create a new SKU with initial stock (requires API key)
- **POST /stock/adjust** - Adjust stock for a SKU (requires API key)
- **POST /reservations** - Create a reservation with idempotency (requires API key)
- **POST /reservations/{id}/confirm** - Confirm a pending reservation (requires API key)
- **POST /reservations/{id}/cancel** - Cancel a reservation (requires API key)
- **GET /orders** - Get paginated list of orders (requires API key)

## Authentication

All mutating endpoints require an `X-API-Key` header. Default test key is `test-api-key`.

## Key Features

- Idempotent reservations via idempotency keys
- Automatic expiration of reservations after 300 seconds
- Stock management with overflow protection
- Order tracking tied to confirmed reservations
- Paginated order listing
