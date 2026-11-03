"""
AI Interview Feedback MVP - FastAPI Main Entry Point

This is the main entry point for the FastAPI backend application.
It creates the app instance, configures middleware, and registers routes.

Author: Member 1 (Backend API)

Usage:
    uvicorn app.main:app --reload --port 8000
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, UPLOAD_DIR
from app.api.v1 import router as api_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.admin import router as admin_router
from app.api.history import router as history_router
from app.api.reports import router as reports_router
from app.models.db import init_db
from app.services.storage_service import init_storage_buckets
from app.logging_config import get_logger

# Suppress warnings from google.generativeai
import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

logger = get_logger(__name__)


# ===========================================
# Application Lifespan (Startup/Shutdown)
# ===========================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Manage application lifespan events.
    
    On startup:
        - Initialize database tables
        - Create upload directories
        - Initialize Supabase storage (optional)
        - Note: ML models are loaded lazily on first request
    
    On shutdown:
        - Log shutdown event
    """
    # ===== STARTUP =====
    logger.info("Starting AI Interview Feedback API...")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"LLM provider: {settings.llm_provider}")
    logger.info(f"Transcription provider: {settings.transcription_provider}")
    
    # Initialize Supabase client (only needs URL + anon key!)
    from app.models.supabase_client import init_supabase
    try:
        init_supabase()
        logger.info("[OK] Supabase connected (REST API - no database password needed!)")
    except Exception as e:
        logger.error(f"Supabase initialization failed: {e}")
        logger.error("Check SUPABASE_URL and SUPABASE_KEY in .env")
        raise
    
    # Create upload directory if it doesn't exist
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        logger.info(f"[OK] Upload directory ready at {UPLOAD_DIR}")
    except Exception as e:
        logger.error(f"Failed to create upload directory: {e}", exc_info=True)
        raise
    
    logger.info("[OK] ML models will be loaded lazily on first request")
    logger.info("[OK] API fully initialized and ready to accept requests")
    if settings.debug:
        logger.info("[DOCS] API documentation: http://localhost:8000/docs")
    
    yield  # Application runs here
    
    # ===== SHUTDOWN =====
    logger.info("Shutting down AI Interview Feedback API...")


# ===========================================
# Create FastAPI Application
# ===========================================

app = FastAPI(
    title="AI Interview Feedback API",
    description="""
    An AI-powered interview preparation system that provides:
    
    * � **Authentication** - Secure user registration and login via Supabase
    * 📄 **Resume Analysis** - Upload resume and get skill matching with job description
    * 🎙️ **Answer Recording** - Record audio answers to interview questions
    * 📊 **6-Score System** - Content, Delivery, Communication, Voice, Confidence, Structure
    * 💡 **AI Feedback** - Receive personalized tips from Google Gemini
    * 📈 **Progress Dashboard** - Track improvement over time with analytics
    """,
    version="1.0.0",
    lifespan=lifespan,
    # Interactive docs list every endpoint; only expose them in local development
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None
)


# ===========================================
# CORS Middleware Configuration
# ===========================================

# Configure CORS to allow frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)


# ===========================================
# Register API Routes
# ===========================================

# Include all API v1 routes under /api/v1 prefix
app.include_router(api_router, prefix="/api/v1", tags=["API v1"])

# Include authentication routes
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])

# Include dashboard routes (protected, requires auth)
app.include_router(dashboard_router, prefix="/api/v1", tags=["Dashboard"])

# Include admin routes for question management
app.include_router(admin_router, prefix="/api/v1", tags=["Admin"])

# Include history routes for attempts, progress, and improvement tracking
app.include_router(history_router, prefix="/api/v1", tags=["History & Progress"])

# Include reports routes for PDF generation and report management
app.include_router(reports_router, prefix="/api/v1", tags=["Reports"])


# ===========================================
# Root Endpoints
# ===========================================

@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint - returns welcome message and API info.
    
    Returns:
        dict: Welcome message with links to documentation
    """
    return {
        "message": "Welcome to AI Interview Feedback API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
        dict: Health status of the API
    """
    return {
        "status": "healthy",
        "service": "ai-interview-feedback-api"
    }
