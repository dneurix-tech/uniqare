from fastapi import FastAPI

from app.database import engine, Base
from app.routers import products, orders, coupons
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Uniqare Store API",
    description="Backend API for hair products store",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://uniqare.vercel.app",
        "https://uniqare-git-main-dn13.vercel.app",
        "https://uniqare-qdos2dmbw-dn13.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(coupons.router)


@app.get("/")
def home():
    return {"message": "Uniqare Store API is running"}