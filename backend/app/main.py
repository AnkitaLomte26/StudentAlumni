from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.database import engine
from app.models import AlumniProfile, StudentProfile, User  # noqa: F401
from app.routes import auth_router, profiles_router
from app.routes.professional import router as professional_router
from app.routes.discovery import router as discovery_router
from app.routes.verification import router as verification_router
from app.routes.networking import router as networking_router
from app.routes.messaging import router as messaging_router
from app.routes.realtime import router as realtime_router
from app.services.realtime import manager
from app.utils.http_security import HTTPSecurityMiddleware
from app.utils.upload_limit import UploadLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("platform")


def check_database() -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "connected"
    except Exception:
        log.error("database_unreachable")
        return "disconnected"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    status_value = check_database()
    if status_value == "connected":
        log.info("startup database=connected environment=%s", settings.ENVIRONMENT)
    else:
        log.error("startup database=unreachable")
    yield
    await manager.close_user()
    log.info("shutdown")


app = FastAPI(
    title="Student–Alumni Networking Platform",
    description="Student–alumni networking with persistent REST messaging and authenticated live delivery",
    version="0.6.0",
    lifespan=lifespan,
)

app.add_middleware(HTTPSecurityMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="session",
    max_age=settings.SESSION_MAX_AGE,
    same_site=settings.SESSION_SAME_SITE,
    https_only=settings.SESSION_HTTPS_ONLY,
)

app.add_middleware(UploadLimitMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host.strip() for host in settings.ALLOWED_HOSTS.split(",")])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    messages = []
    for error in exc.errors():
        location = error.get("loc", ())
        field = location[-1] if location else "input"
        messages.append(f"{field}: {error.get('msg', 'Invalid value')}")
    detail = "; ".join(messages) if messages else "Invalid request."
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": detail})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "database": check_database(),
    }


@app.get("/readiness")
def readiness():
    reachable = check_database() == "connected"
    return JSONResponse({"status":"ready" if reachable else "not_ready", "database":"connected" if reachable else "disconnected"}, status_code=200 if reachable else 503)


app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(professional_router)
app.include_router(discovery_router)
app.include_router(verification_router)
app.include_router(networking_router)
app.include_router(messaging_router)
app.include_router(realtime_router)
