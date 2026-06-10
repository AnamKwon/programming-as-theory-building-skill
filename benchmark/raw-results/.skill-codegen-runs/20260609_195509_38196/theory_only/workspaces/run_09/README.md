# Commerce Service

An inventory reservation and order orchestration API for small commerce backends.

## Features

- **Inventory Management**: Create SKUs and manage stock levels
- **Reservation System**: Reserve inventory with automatic expiration
- **Idempotency**: Safe retry semantics via idempotency keys
- **Order Orchestration**: Confirm, cancel, and track orders
- **API Key Security**: Protect mutating endpoints
- **Pagination**: Efficient order listing

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Run Server

```bash
uvicorn src.commerce_service.app:app --reload
```

Server runs on `http://localhost:8000`. API docs at `/docs`.

### Run Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Health Check
- `GET /health` — Service health check

### SKU Management
- `POST /skus` — Create a new SKU (requires API key)
- `POST /skus/{sku_id}/adjust` — Adjust stock level (requires API key)

### Reservations
- `POST /reservations` — Create a reservation (requires API key)
- `POST /reservations/{reservation_id}/confirm` — Confirm reservation (requires API key)
- `POST /reservations/{reservation_id}/cancel` — Cancel reservation (requires API key)

### Orders
- `GET /orders` — List orders with pagination
- `GET /orders/{order_id}` — Get a single order

## Configuration

Set `API_KEY` environment variable for authentication:

```bash
export API_KEY=your-secret-key
```

Default: `"test-key"` (development only).

## Architecture

- **Models** — Pydantic schemas for requests/responses
- **Repository** — SQLite database access layer
- **Service** — Business logic and state transitions
- **App** — FastAPI application and routes
- **Security** — API key validation
