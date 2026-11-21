from pydantic import BaseModel, Field
from typing import List, Optional
import datetime


class OrderCreate(BaseModel):
    """创建订单的请求体 Schema。"""

    user_id: str = Field(..., description="用户ID")
    total_amount: float = Field(..., ge=0, description="订单总金额")
    items: List[dict] = Field(default_factory=list, description="订单项列表")


class OrderResponse(BaseModel):
    """订单响应数据 Schema。"""

    id: str
    user_id: str
    status: str
    total_amount: float
    items: List[dict]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class OrderUpdateStatus(BaseModel):
    """更新订单状态的请求体 Schema。"""

    new_status: str = Field(..., description="新的订单状态")