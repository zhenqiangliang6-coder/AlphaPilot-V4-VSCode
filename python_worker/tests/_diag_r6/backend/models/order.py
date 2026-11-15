from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, func
from backend.database import Base
from backend.models.enums import OrderStatus

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    status = Column(String, default=OrderStatus.PENDING.value, nullable=False)
    total_amount = Column(Float, nullable=False)
    items = Column(JSON, default=lambda: [], nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)