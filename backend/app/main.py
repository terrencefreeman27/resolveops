"""FastAPI application."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import requests as requests_api
from .api import session as session_api
from .review import ReviewError
from .workflow import InvalidTransition

app = FastAPI(title="ResolveOps API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    """Cookie-authenticated mutations must carry a custom header that cross-site forms cannot send."""
    if request.method in MUTATING and request.url.path.startswith("/api/") and request.headers.get("x-resolveops") != "1":
        return JSONResponse({"detail": "Missing X-ResolveOps header."}, status_code=403)
    return await call_next(request)


@app.exception_handler(ReviewError)
async def review_error(_: Request, exc: ReviewError):
    return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)


@app.exception_handler(InvalidTransition)
async def invalid_transition(_: Request, exc: InvalidTransition):
    return JSONResponse({"detail": str(exc)}, status_code=409)


app.include_router(session_api.router)
app.include_router(requests_api.router)
