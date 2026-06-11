# Commerce Service

A FastAPI-based inventory and order management service.

## Setup

Install dependencies:
```bash
pip install -e .
pip install -e ".[dev]"
```

## Running

Start the server:
```bash
uvicorn src.commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

## Testing

Run tests:
```bash
pytest
```

## Environment Variables

- `API_TOKEN`: API token for authentication (default: "test-token-secret")

## API Endpoints

- `GET /health` - Health check
- `POST /skus` - Create a new SKU
- `POST /stock/adjust` - Adjust stock level
- `POST /reservations` - Create a reservation
- `POST /reservations/{id}/confirm` - Confirm a reservation
- `POST /reservations/{id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (paginated)
