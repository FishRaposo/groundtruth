from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.keys import router as keys_router
from app.api.queries import router as queries_router

__all__ = ["documents_router", "health_router", "keys_router", "queries_router"]
