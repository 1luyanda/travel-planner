"""FastAPI routes."""

from .auth import router as auth_router
from .routes import router

__all__ = ["auth_router", "router"]
