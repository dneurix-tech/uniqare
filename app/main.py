import os

from dotenv import load_dotenv

# Load Railway/local environment variables before importing routers/security.
load_dotenv()

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.routers import (  # noqa: E402
    announcements,
    auth,
    bundles,
    coupons,
    orders,
    products,
    reviews,
)


Base.metadata.create_all(bind=engine)


def _is_enabled(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "").strip()

    if configured:
        return [
            origin.strip().rstrip("/")
            for origin in configured.split(",")
            if origin.strip()
        ]

    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://uniqare.vercel.app",
        "https://uniqare-git-main-dn13.vercel.app",
        "https://uniqare-qdos2dmbw-dn13.vercel.app",
    ]


api_docs_enabled = _is_enabled(
    os.getenv("ENABLE_API_DOCS"),
    default=False,
)

app = FastAPI(
    title="Uniqare Store API",
    description="Backend API for hair products store",
    version="1.1.0",
    docs_url="/docs" if api_docs_enabled else None,
    redoc_url="/redoc" if api_docs_enabled else None,
    openapi_url="/openapi.json" if api_docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "X-Order-Token",
    ],
)


@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next,
):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )

    if request.url.path.startswith(("/auth/", "/orders/")):
        response.headers.setdefault(
            "Cache-Control",
            "no-store, max-age=0",
        )

    return response


app.include_router(auth.router)
app.include_router(products.router)
app.include_router(bundles.router)
app.include_router(orders.router)
app.include_router(coupons.router)
app.include_router(reviews.router)
app.include_router(announcements.router)


@app.get("/")
def home():
    return {
        "message": "Uniqare Store API is running",
    }
