import datetime
from sqlalchemy import Column, String, Float, JSON, DateTime
from backend.database import Base
from backend.models.enums import OrderStatus

# Re-export OrderStatus to satisfy the contract requirement in order.py context if needed by imports
__all__ = ["Order", "OrderStatus"]


class Order(Base):
    """SQLAlchemy ORM 模型：订单。"""

    __tablename__ = "orders"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default=OrderStatus.PENDING.value)
    total_amount = Column(Float, nullable=False, default=0.0)
    items = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)