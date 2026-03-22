"""FastAPI application entry point.

Sets up the API server with CORS middleware for the React frontend
and mounts the document scanning route at /api.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.scan import router as scan_router

app = FastAPI(title="ID Document Scanner API")

# Allow requests from the Vite dev server and common local ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan_router, prefix="/api")


@app.get("/")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "ID Document Scanner API"}
