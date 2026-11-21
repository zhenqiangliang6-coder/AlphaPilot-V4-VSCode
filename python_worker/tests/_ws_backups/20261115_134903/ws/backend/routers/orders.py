from typing import List
from backend.models.order import Order
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.order import Order, OrderStatus
from backend.schemas.order import OrderCreate, OrderResponse, OrderUpdateStatus

router = APIRouter()


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_200_OK)
def create_order(order_in: OrderCreate, db: Session = Depends(get_db)):
    """
    创建新订单。
    """
    # Generate a unique ID for the order
    order_id = str(uuid.uuid4())
    
    db_order = Order(
        id=order_id,
        user_id=order_in.user_id,
        status=OrderStatus.PENDING.value,
        total_amount=order_in.total_amount,
        items=order_in.items,
    )
    
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    
    return db_order


@router.get("/", response_model=List[OrderResponse], status_code=status.HTTP_200_OK)
def list_orders(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    获取订单列表。
    """
    orders = db.query(Order).offset(skip).limit(limit).all()
    return orders


@router.get("/{order_id}", response_model=OrderResponse, status_code=status.HTTP_200_OK)
def read_order(order_id: str, db: Session = Depends(get_db)):
    """
    根据 ID 查询单个订单。
    """
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if db_order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return db_order


@router.put("/{order_id}/status", response_model=OrderResponse, status_code=status.HTTP_200_OK)
def update_order_status(
    order_id: str, 
    order_update: OrderUpdateStatus, 
    db: Session = Depends(get_db)
):
    """
    更新订单状态。包含状态机逻辑校验。
    """
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if db_order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    current_status_enum = OrderStatus(db_order.status)
    new_status_value = order_update.new_status

    # Validate if the new status is a valid transition
    allowed_next_states = current_status_enum.next_states()
    
    if new_status_value not in allowed_next_states:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status transition from '{current_status_enum.value}' to '{new_status_value}'. Allowed states: {allowed_next_states}"
        )

    db_order.status = new_status_value
    db.commit()
    db.refresh(db_order)
    
    return db_order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(order_id: str, db: Session = Depends(get_db)):
    """
    删除订单。
    """
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if db_order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    
    db.delete(db_order)
    db.commit()
    return