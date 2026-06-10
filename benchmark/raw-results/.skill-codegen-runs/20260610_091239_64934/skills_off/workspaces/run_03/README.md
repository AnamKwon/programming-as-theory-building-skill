# Commerce Service

Inventory reservation and order orchestration API.

## Features

- SKU creation and inventory management
- Inventory reservations with idempotency
- Reservation confirmation and cancellation
- Order lookup with pagination
- API key authentication for mutations
- Automatic reservation expiration (15 minutes)
- Clear HTTP error responses

## Installation

```bash
pip install -e .
pip install -e ".[dev]"  # for testing
```

## Running

```bash
uvicorn commerce_service.app:app --reload
```

The API will be available at `http://localhost:8000`.

- Health check: `GET /health`
- Interactive docs: `http://localhost:8000/docs`

## API Endpoints

- `POST /skus` - Create a SKU
- `POST /stock/{sku_id}/adjust` - Adjust stock
- `POST /reservations` - Create a reservation
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation
- `GET /orders` - List orders (paginated)
- `GET /orders/{order_id}` - Get order details

All mutation endpoints require an `X-API-Key` header.

## Testing

```bash
pytest
```
