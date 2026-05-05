from fastapi import FastAPI
import os
from router.model_router import app as router_app

app = FastAPI(title="Model Router API", description="API for routing model requests", version="1.0")

# include routes declared in the router sub-app
app.include_router(router_app.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Model Router API!"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("model_router_api:app", host="0.0.0.0", port=port, reload=True)"