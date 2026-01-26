"""Battery Smart Voicebot API - Main Application."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time

from .core.config import settings
from .core.database import init_db, close_db
from .routers import swaps, stations, subscriptions, dsk, drivers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Battery Smart Voicebot API...")
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization skipped: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Battery Smart Voicebot API...")
    await close_db()
    logger.info("Database connections closed")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    Battery Smart Voicebot API for handling Tier-1 driver support queries.

    ## Features
    - **Swap History**: View past battery swaps and invoice explanations
    - **Station Finder**: Find nearest stations with real-time availability
    - **Subscriptions**: Check plan validity, renewals, and pricing
    - **DSK & Leaves**: Find service centers and manage leave requests

    ## Languages
    Supports Hindi (hi), English (en), and Hinglish (hi-en) responses.
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    """Add request timing header."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal error occurred",
            "detail_hi": "Ek internal error hua"
        }
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "service": "battery-smart-voicebot-api"
    }


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Battery Smart Voicebot API",
        "message_hi": "Battery Smart Voicebot API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


# Include routers
app.include_router(drivers.router, prefix="/api/v1")
app.include_router(swaps.router, prefix="/api/v1")
app.include_router(stations.router, prefix="/api/v1")
app.include_router(subscriptions.router, prefix="/api/v1")
app.include_router(dsk.router, prefix="/api/v1")


# Voicebot-specific endpoints
@app.post("/api/v1/voice/session/start", tags=["Voice"])
async def start_voice_session(phone_number: str):
    """
    Start a new voice session.

    Called when a call is received from Amazon Connect.
    """
    return {
        "session_id": f"voice-{phone_number}-{int(time.time())}",
        "greeting": "Namaste! Battery Smart mein aapka swagat hai. Main aapki kaise madad kar sakti hoon?",
        "greeting_en": "Hello! Welcome to Battery Smart. How can I help you today?",
        "language_detected": "hi-en"
    }


@app.post("/api/v1/voice/session/end", tags=["Voice"])
async def end_voice_session(session_id: str, resolution_status: str = "resolved"):
    """
    End a voice session.

    Called when a call ends or is transferred.
    """
    return {
        "session_id": session_id,
        "status": "ended",
        "resolution_status": resolution_status,
        "farewell": "Dhanyavaad! Battery Smart ko choose karne ke liye shukriya.",
        "farewell_en": "Thank you for choosing Battery Smart. Have a great day!"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )