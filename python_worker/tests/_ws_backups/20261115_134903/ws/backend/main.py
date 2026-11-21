from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure models are imported to register them in Base.metadata before create_all
import backend.models.order  # noqa: F401
from backend.database import engine, Base
from backend.routers import orders

# Create tables if they don't exist (idempotent)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="ShopFlow API")

# CORS Middleware for development convenience
origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Orders Router with prefix
app.include_router(orders.router, prefix="/orders", tags=["orders"])


@app.get("/")
def read_root():
    return {"message": "ShopFlow API is running"}