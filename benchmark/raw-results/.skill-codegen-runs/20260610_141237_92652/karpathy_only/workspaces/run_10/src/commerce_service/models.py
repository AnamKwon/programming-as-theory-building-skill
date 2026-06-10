from pydantic import BaseModel


class SKUCreateRequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int


class StockAdjustRequest(BaseModel):
    sku: str
    amount: int


class ReservationCreateRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: str


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int


class HealthResponse(BaseModel):
    status: str
