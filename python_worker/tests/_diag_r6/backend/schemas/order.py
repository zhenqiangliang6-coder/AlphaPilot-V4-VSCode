from datetime import datetime
from pydantic import BaseModel, field_validator
from typing import List, Optional
from backend.models.enums import OrderStatus

class OrderCreate(BaseModel):
    user_id: str
    total_amount: float
    items: List[dict] = []
    status: OrderStatus = OrderStatus.PENDING

    @field_validator('total_amount')
    def total_must_be_positive(cls, v):
        if v < 0:
            raise ValueError('total_amount must be >= 0')
        return v

class OrderResponse(BaseModel):
    id: int
    user_id: str
    status: OrderStatus
    total_amount: float
    items: List[dict]
    created_at: datetime

    class Config:
        from_attributes = True

class OrderUpdateStatus(BaseModel):
    new_status: str

    @field_validator('new_status')
    def status_must_be_valid(cls, v):
        try:
            OrderStatus(v)
        except ValueError:
            raise ValueError(f"Invalid status: {v}")
        return v