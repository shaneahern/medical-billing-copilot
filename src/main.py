"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="Medical Billing Copilot",
    description="AI-powered Q&A web application for SMB medical billing teams",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
