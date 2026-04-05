# api/auth.py
# Simple API key authentication for KairosIQ API
# Customers get an API key when they subscribe

import os
import psycopg2
import sys
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# For MVP — hardcoded test key
# In production this would be stored in the database
TEST_API_KEY = "kairosiq-test-key-2026"

def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    """
    Verify the API key from the request header.
    Returns the api_key if valid, raises HTTPException if not.
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Pass X-API-Key header."
        )

    if api_key != TEST_API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key."
        )

    return api_key