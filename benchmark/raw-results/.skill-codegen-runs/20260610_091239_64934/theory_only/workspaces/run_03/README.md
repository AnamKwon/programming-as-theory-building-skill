# Commerce Service

Inventory reservation and order orchestration API for small commerce backends.

## Setup

Install dependencies:
```bash
pip install -e ".[dev]"
```

## Running

Start the API:
```bash
python -m uvicorn src.commerce_service.app:app --reload
```

Health check:
```bash
curl http://localhost:8000/health
```

## API Endpoints

### Public
- `GET /health` - Health check

### Authenticated (require X-API-Key header)
- `POST /skus` - Create a SKU
- `POST /stock/{sku_id}/adjust` - Adjust stock
- `POST /reservations` - Create a reservation
- `POST /reservations/{reservation_id}/confirm` - Confirm a reservation
- `POST /reservations/{reservation_id}/cancel` - Cancel a reservation
- `GET /orders` - List orders with pagination

## Key Features

- **Idempotent reservations**: Requests with the same idempotency key return the same result
- **Reservation expiration**: Pending reservations expire after 15 minutes
- **Stock management**: Reservations hold stock; confirmations convert holds to committed
- **Order state machine**: Pending → Confirmed or Cancelled
- **Pagination**: Order listing supports limit and offset
- **API key authentication**: All mutations require X-API-Key header

## Testing

```bash
pytest tests/
```
