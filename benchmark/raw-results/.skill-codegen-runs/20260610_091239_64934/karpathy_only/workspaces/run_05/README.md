# Commerce Service

Inventory reservation and order orchestration API built with FastAPI, Pydantic, and SQLite.

## Features

- **SKU Management**: Create products and adjust stock levels
- **Reservations**: Reserve inventory with expiration and idempotency
- **Orders**: Track reservations as orders through their lifecycle
- **API Security**: API key authentication for mutating endpoints
- **Pagination**: List orders with limit/offset pagination

## Quick Start

### Install

```bash
pip install -e .
pip install -e ".[dev]"  # for testing
```

### Run

```bash
python -m uvicorn src.commerce_service.app:app --reload
```

The API will be available at http://localhost:8000. API docs at http://localhost:8000/docs.

### Test

```bash
pytest
```

## API Endpoints

### Health

- `GET /health` - Service health check

### SKUs

- `POST /skus` - Create a SKU (requires API key)
- `POST /skus/{sku_id}/stock` - Adjust stock (requires API key)

### Reservations

- `POST /reservations` - Create a reservation (requires API key, with idempotency key)
- `POST /reservations/{reservation_id}/confirm` - Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` - Cancel reservation (requires API key)

### Orders

- `GET /orders` - List orders (pagination via limit/offset)
- `GET /orders/{order_id}` - Get order details

## Configuration

Set the `API_KEY` environment variable for authentication:

```bash
export API_KEY=sk-test-key
```

Default reservation TTL is 15 minutes. Adjust `RESERVATION_TTL_MINUTES` in the environment.

## Database

SQLite database is created at `./commerce.db` on first run.
