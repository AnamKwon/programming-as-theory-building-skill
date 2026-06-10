# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Features

- SKU creation and management
- Real-time stock adjustment
- Reservation with expiration and confirmation workflow
- Order orchestration with pagination
- Idempotency key support for safe retries
- API-key authentication for mutations
- SQLite-backed persistence

## Quick Start

### Installation

```bash
pip install -e .
```

### Run Server

```bash
uvicorn commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`.

### API Endpoints

**Health Check**
```
GET /health
```

**SKU Management**
```
POST /skus
GET /skus/{sku_id}
POST /skus/{sku_id}/adjust
```

**Reservations**
```
POST /reservations
POST /reservations/{reservation_id}/confirm
POST /reservations/{reservation_id}/cancel
```

**Orders**
```
GET /orders?skip=0&limit=20
```

### Authentication

Mutating endpoints require an `X-API-Key` header:

```bash
curl -X POST http://localhost:8000/skus \
  -H "X-API-Key: secret-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "Widget", "quantity": 100}'
```

## Testing

```bash
pytest tests/
```

## Architecture

- **models.py**: Pydantic data models
- **repository.py**: SQLite data access
- **service.py**: Business logic and workflows
- **security.py**: API key validation
- **app.py**: FastAPI application and routes
