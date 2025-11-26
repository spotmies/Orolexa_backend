# Routers package
from . import auth_router
from . import analysis_router
from . import health_analytics_router
from . import firmware_router

__all__ = [
    "auth_router",
    "analysis_router",
    "health_analytics_router",
    "firmware_router"
]