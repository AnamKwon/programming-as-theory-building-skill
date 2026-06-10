import os
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base, SKUResponse, StockAdjustment, ReservationCreate, ReservationResponse, OrderResponse, OrderListResponse
from .repository import Repository
from .service import CommerceService, InsufficientStockError, ReservationNotFoundError, ReservationExpiredError, InvalidStateTransitionError
from .security import verify_api_key

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./commerce.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service(db: Session = Depends(get_db)) -> CommerceService:
    return CommerceService(Repository(db))


app = FastAPI(title="Commerce Service", version="0.1.0")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/skus", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
def create_sku(
    sku: dict,
    service: CommerceService = Depends(get_service),
):
    try:
        sku_id = sku.get("sku_id")
        stock_available = sku.get("stock_available")
        if not sku_id or stock_available is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sku_id and stock_available are required",
            )
        result = service.create_sku(sku_id, stock_available)
        return SKUResponse(
            sku_id=result.sku_id,
            stock_available=result.stock_available,
            created_at=result.created_at,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/skus/{sku_id}/stock", response_model=SKUResponse, dependencies=[Depends(verify_api_key)])
def adjust_stock(
    sku_id: str,
    adjustment: StockAdjustment,
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.adjust_stock(sku_id, adjustment.quantity_delta)
        return SKUResponse(
            sku_id=result.sku_id,
            stock_available=result.stock_available,
            created_at=result.created_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
def create_reservation(
    reservation: ReservationCreate,
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.create_reservation(
            sku_id=reservation.sku_id,
            quantity=reservation.quantity,
            idempotency_key=reservation.idempotency_key,
        )
        return ReservationResponse(
            reservation_id=result.reservation_id,
            sku_id=result.sku_id,
            quantity=result.quantity,
            state=result.state,
            expires_at=result.expires_at,
            created_at=result.created_at,
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/confirm", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
def confirm_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.confirm_reservation(reservation_id)
        return ReservationResponse(
            reservation_id=result.reservation_id,
            sku_id=result.sku_id,
            quantity=result.quantity,
            state=result.state,
            expires_at=result.expires_at,
            created_at=result.created_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ReservationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationResponse, dependencies=[Depends(verify_api_key)])
def cancel_reservation(
    reservation_id: str,
    service: CommerceService = Depends(get_service),
):
    try:
        result = service.cancel_reservation(reservation_id)
        return ReservationResponse(
            reservation_id=result.reservation_id,
            sku_id=result.sku_id,
            quantity=result.quantity,
            state=result.state,
            expires_at=result.expires_at,
            created_at=result.created_at,
        )
    except ReservationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get("/orders", response_model=OrderListResponse)
def list_orders(
    skip: int = 0,
    limit: int = 10,
    service: CommerceService = Depends(get_service),
):
    if limit > 100:
        limit = 100
    if skip < 0:
        skip = 0

    orders, total = service.list_orders(skip, limit)
    return OrderListResponse(
        items=[
            OrderResponse(
                order_id=order.order_id,
                reservation_id=order.reservation_id,
                sku_id=order.sku_id,
                quantity=order.quantity,
                state=order.state,
                created_at=order.created_at,
            )
            for order in orders
        ],
        total=total,
        skip=skip,
        limit=limit,
    )
