"""FastAPI application: CORS, routers, health."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .generator import ollama_status

app = FastAPI(title="SmartTest", version="1.0.0")
_s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_s.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    status = ollama_status()
    return {
        "status": "ok",
        "llm_provider": s.llm_provider,
        "ollama_reachable": status["reachable"],
        "ollama_base_url": s.ollama_base_url,
        "model": s.ollama_model,
        "model_installed": s.ollama_model in status["models"],
        "error": status["error"],
    }


@app.get("/api/models")
def models() -> dict:
    status = ollama_status()
    return {"reachable": status["reachable"], "models": status["models"], "default": get_settings().ollama_model}
