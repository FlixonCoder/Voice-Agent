from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes_agent import router as agent_router
from api.routes_health import router as health_router
from config import get_settings

_settings = get_settings()

app = FastAPI(title="Voice AI Agent")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.CORS_ALLOW_ORIGINS if _settings.CORS_ALLOW_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router, tags=["health"])
app.include_router(agent_router, tags=["agent"])