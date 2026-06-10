# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- **SKU Management**: Create and manage product inventory
- **Stock Adjustment**: Update inventory levels
- **Reservation System**: Temporary holds on inventory with automatic expiration
- **Order Fulfillment**: Confirm reservations into orders
- **API Key Security**: Protect mutating endpoints
- **Idempotency**: Safe retry semantics via idempotency keys
- **Pagination**: Efficient order lookups

## Architecture

```
app.py          → FastAPI routes, HTTP layer
├─ service.py   → Business logic (stock rules, state transitions)
├─ security.py  → Authentication (API key validation)
├─ models.py    → Pydantic schemas & SQLAlchemy ORM
└─ repository.py → Database access layer
```

## Quick Start

### Install

```bash
pip install -e ".[dev]"
```

### Run

```bash
python -m uvicorn commerce_service.app:app --reload
```

### Test

```bash
pytest -v
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/skus` | Create SKU |
| POST | `/skus/{sku_id}/stock` | Adjust stock |
| POST | `/reservations` | Create reservation |
| POST | `/reservations/{reservation_id}/confirm` | Confirm reservation |
| POST | `/reservations/{reservation_id}/cancel` | Cancel reservation |
| GET | `/orders` | List orders (paginated) |

## Design Principles

- **Layered Architecture**: Clear separation between HTTP, service, and data layers
- **Repository Pattern**: All database access isolated in one module
- **Idempotency**: Mutation endpoints support safe retries
- **Expiration**: Reservations expire automatically after TTL
- **State Machine**: Strict order state transitions (pending → confirmed → expired/cancelled)

## Environment

```
COMMERCE_API_KEY=your-key-here
DATABASE_URL=sqlite:///./commerce.db
```
