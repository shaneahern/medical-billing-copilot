"""FastAPI application entry point."""

from fastapi import FastAPI

from src.routers import auth_router, query_router, session_router

app = FastAPI(
    title="Medical Billing Copilot",
    description="AI-powered Q&A web application for SMB medical billing teams",
    version="0.1.0",
)

# Include routers
app.include_router(auth_router)
app.include_router(query_router)
app.include_router(session_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
