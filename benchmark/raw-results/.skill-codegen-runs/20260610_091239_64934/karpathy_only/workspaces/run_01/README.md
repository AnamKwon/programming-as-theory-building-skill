# Commerce Service

An inventory reservation and order orchestration API for small commerce backends.

## Features

- **SKU Management**: Create and manage product SKUs.
- **Stock Management**: Adjust available stock and track reservations.
- **Reservation System**: Create, confirm, and cancel reservations with automatic expiration.
- **Order Orchestration**: Transition orders through defined states.
- **Idempotency**: Built-in idempotency key support for safe retries.
- **API Key Security**: Protect mutating endpoints with API key authentication.

## Quick Start

### Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

### Running the Service

```bash
uvicorn src.commerce_service.app:app --reload
```

The service runs on `http://localhost:8000`.

### Running Tests

```bash
pytest
```

## API Endpoints

### Health

- `GET /health` — Service health check.

### SKUs

- `POST /skus` — Create a new SKU. Requires API key.
- **Request body:** `{"name": "string", "price": float}`

### Stock

- `POST /stock/{sku_id}/adjust` — Adjust stock quantity. Requires API key.
- **Request body:** `{"quantity": int}`

### Reservations

- `POST /reservations` — Create a reservation for a SKU. Requires API key.
- **Request body:** `{"sku_id": int, "quantity": int, "idempotency_key": "string"}`
- **Response:** `{"id": int, "sku_id": int, "quantity": int, "status": "pending", "expires_at": "timestamp"}`

- `POST /reservations/{id}/confirm` — Confirm a pending reservation. Requires API key.
- **Response:** `{"id": int, "status": "confirmed"}`

- `POST /reservations/{id}/cancel` — Cancel a reservation. Requires API key.
- **Response:** `{"id": int, "status": "cancelled"}`

### Orders

- `GET /orders` — List orders with pagination. Requires API key.
- **Query params:** `skip=0&limit=20`
- **Response:** `{"items": [...], "total": int}`

## Architecture

- **Models**: Pydantic data models for validation.
- **Repository**: SQLite-backed data access layer.
- **Service**: Business logic and state transitions.
- **API**: FastAPI application with security.

## Environment

Set the `API_KEY` environment variable to protect mutating endpoints:

```bash
export API_KEY=your-secret-key
```

Default: `test-api-key`.
