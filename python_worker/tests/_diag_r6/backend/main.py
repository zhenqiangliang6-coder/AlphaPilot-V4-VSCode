from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import orders
from backend.database import Base, engine, init_db, health_check, get_db

init_db()

app = FastAPI(title="ShopFlow API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.orders_router, prefix="/orders")

@app.get("/")
def read_root():
    return {"message": "ShopFlow API is running"}

@app.get("/health")
def health_check_endpoint():
    db_ok = health_check()
    if not db_ok:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unreachable")
    return {"status": "ok", "db": "ready"}