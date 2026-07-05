from fastapi import FastAPI

from app.database import engine, Base
from app.routers import products, orders, coupons

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Uniqare Store API",
    description="Backend API for hair products store",
    version="1.0.0"
)

app.include_router(products.router)
app.include_router(orders.router)
app.include_router(coupons.router)


@app.get("/")
def home():
    return {"message": "Uniqare Store API is running"}