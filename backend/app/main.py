"""
iEZ FastAPI Application
Main entry point for the backend API.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from contextlib import asynccontextmanager

from .config import settings
from .database import init_db
from .auth.router import router as auth_router
from .routers.validator import router as validator_router
from .routers.datasheet import router as datasheet_router
from .routers.coversheet import router as coversheet_router
from .routers.instrument_list import router as instrument_list_router
from .routers.io_list import router as io_list_router
from .routers.cable_schedule import router as cable_schedule_router
from .routers.loop_wiring import router as loop_wiring_router
from .routers.sdie import router as sdie_router
from .routers.sop_datasheet import router as sop_datasheet_router
from .routers.lt_radar import router as lt_radar_router
from .routers.deploy import router as deploy_router
from .routers.admin_users import router as admin_router
from .routers.approvals import router as approvals_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup: Initialize database
    print("🚀 Starting iEZ API...")
    init_db()
    print("✅ Database initialized")
    
    yield
    
    # Shutdown
    print("👋 Shutting down iEZ API...")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for iEZ - Instrumentation Engineering EZ document generator",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# Include routers
app.include_router(auth_router, prefix="/api")
app.include_router(validator_router, prefix="/api")
app.include_router(datasheet_router, prefix="/api")
app.include_router(coversheet_router, prefix="/api")
app.include_router(instrument_list_router, prefix="/api")
app.include_router(io_list_router, prefix="/api")
app.include_router(cable_schedule_router, prefix="/api")
app.include_router(loop_wiring_router, prefix="/api")
app.include_router(sdie_router, prefix="/api")
app.include_router(sop_datasheet_router, prefix="/api")
app.include_router(lt_radar_router, prefix="/api")
app.include_router(deploy_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(approvals_router, prefix="/api")


@app.get("/")
def root():
    """Root endpoint - API health check."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
