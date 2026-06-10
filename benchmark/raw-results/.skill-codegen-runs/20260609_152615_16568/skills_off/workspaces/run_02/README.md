# Commerce Service

Inventory reservation and order orchestration API built with FastAPI.

## Features

- **SKU Management**: Create and list SKUs
- **Stock Management**: Adjust inventory levels per SKU
- **Reservations**: Reserve stock with expiration, confirm, or cancel
- **Orders**: View orders with pagination
- **Idempotency**: Safe retry semantics for reservation requests
- **Authorization**: API key validation for mutating operations

## Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`.

## Testing

```bash
pytest
```

## API Key

Set `API_KEY` environment variable for authorization:

```bash
export API_KEY=test-key-123
```

All mutating endpoints (POST, PATCH, DELETE) require the `X-API-Key` header.

## Health Check

```bash
curl http://localhost:8000/health
```

## Core Concepts

**Reservations** have lifecycle: PENDING → CONFIRMED → COMPLETED, or CANCELLED.
- PENDING reservations expire after 30 minutes.
- Cannot reserve more stock than available.
- Confirming a reservation deducts from inventory and creates an order.

**Orders** track order state and total reserved/confirmed quantities.
- Pagination available via `skip` and `limit` query parameters.
