# Commerce Service

A FastAPI-based inventory reservation and order orchestration service.

## Features

- SKU and stock management
- Inventory reservations with expiration
- Order state transitions (reserved → confirmed → completed)
- Idempotent operations via idempotency keys
- API key security on mutations
- Pagination for order lookups
- SQLite persistence

## Installation

```bash
pip install -e ".[dev]"
```

## Running

```bash
python -m uvicorn commerce_service.app:app --reload
```

API docs available at `http://localhost:8000/docs`

## Testing

```bash
pytest
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/skus` | Create SKU |
| POST | `/stock/adjust` | Adjust stock |
| POST | `/reservations` | Create reservation |
| POST | `/reservations/{id}/confirm` | Confirm reservation |
| POST | `/reservations/{id}/cancel` | Cancel reservation |
| GET | `/orders` | List orders (paginated) |

## Architecture

- `models.py`: Pydantic request/response schemas
- `repository.py`: Data access layer (SQLite)
- `service.py`: Business logic and state transitions
- `security.py`: API key validation
- `app.py`: FastAPI application and routes
