# api/main.py
# KairosIQ FastAPI — external customer API
# Run with: uvicorn api.main:app --reload --port 8000

import warnings
warnings.filterwarnings("ignore")

import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from api.routes.signals import router as signals_router
from api.routes.performance import router as performance_router
from api.routes.portfolio import router as portfolio_router

# --- App ---
app = FastAPI(
    title="KairosIQ API",
    description=(
        "Geopolitical intelligence signals derived from prediction markets. "
        "Historical data only. Not investment advice."
    ),
    version="1.0.0"
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes ---
app.include_router(signals_router, prefix="/v1", tags=["Signals"])
app.include_router(performance_router, prefix="/v1", tags=["Performance"])
app.include_router(portfolio_router, prefix="/v1", tags=["Portfolio"])

# --- Health Check ---
@app.get("/")
def root():
    return {
        "name": "KairosIQ API",
        "version": "1.0.0",
        "status": "running",
        "tagline": "Intelligence before the market opens its eyes",
        "docs": "/docs",
        "disclaimer": (
            "Historical data only. Not investment advice. "
            "KairosIQ is a data provider, not a registered investment advisor."
        )
    }

@app.get("/health")
def health():
    return {"status": "healthy"}