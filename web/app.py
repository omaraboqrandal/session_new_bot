"""
Web Panel — FastAPI application factory.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import HTTPException

import database.database as db
from web.security import SecurityMiddleware, check_login_rate_limit, _get_real_ip
from web.auth import validate_token_and_login, require_auth, SESSION_COOKIE

logger = logging.getLogger("web")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — periodic cleanup of expired tokens/sessions."""
    async def cleanup_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                await db.cleanup_expired_tokens()
                await db.cleanup_expired_web_sessions()
            except Exception as e:
                logger.error("Cleanup error: %s", e)

    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="Session Manager Panel",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    # Security middleware
    app.add_middleware(SecurityMiddleware)

    # Templates & static files
    templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
    app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

    # ── Custom exception handler for 401 → redirect to login ─────────────
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        if exc.status_code == 403:
            return templates.TemplateResponse(
                request, "login.html",
                {"token": "", "error": exc.detail or "Access denied"},
                status_code=403,
            )
        return JSONResponse({"error": exc.detail or "Error"}, status_code=exc.status_code)

    # ══════════════════════════════════════════════════════════════════════
    #  AUTH ROUTES
    # ══════════════════════════════════════════════════════════════════════

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, token: str = "", error: str = ""):
        return templates.TemplateResponse(
            request, "login.html", {"token": token, "error": error},
        )

    @app.post("/login")
    async def do_login(request: Request):
        check_login_rate_limit(_get_real_ip(request))
        form = await request.form()
        token = form.get("token", "").strip()
        if not token:
            return templates.TemplateResponse(
                request, "login.html",
                {"token": "", "error": "Token is required"},
                status_code=400,
            )

        try:
            session_id = await validate_token_and_login(token, request)
        except HTTPException as e:
            return templates.TemplateResponse(
                request, "login.html",
                {"token": "", "error": e.detail},
                status_code=e.status_code,
            )

        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=session_id,
            httponly=True,
            secure=False,
            samesite="strict",
            max_age=86400,
        )
        return response

    @app.get("/logout")
    async def logout(request: Request):
        session_id = request.cookies.get(SESSION_COOKIE)
        if session_id:
            try:
                await db.delete_web_session(session_id)
            except Exception:
                pass
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    # ══════════════════════════════════════════════════════════════════════
    #  ROOT REDIRECT
    # ══════════════════════════════════════════════════════════════════════

    @app.get("/", response_class=RedirectResponse)
    async def root():
        return RedirectResponse(url="/dashboard")

    # ══════════════════════════════════════════════════════════════════════
    #  DASHBOARD
    # ══════════════════════════════════════════════════════════════════════

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request, _=Depends(require_auth)):
        from utils.country_utils import get_all_sessions, get_country_display

        all_sessions = get_all_sessions()
        all_statuses = await db.get_all_statuses()
        all_contact = await db.get_all_contact_statuses()
        total = sum(len(v) for v in all_sessions.values())
        countries = len(all_sessions)

        # Spam status counts
        spam_counts = {}
        for s in all_statuses.values():
            spam_counts[s] = spam_counts.get(s, 0) + 1

        # Contact status counts
        contact_counts = {}
        for s in all_contact.values():
            contact_counts[s] = contact_counts.get(s, 0) + 1

        admins = await db.get_all_admins()
        recent_logs = await db.get_recent_logs(20)

        # Scheduler settings
        sched_info = {
            "auto_check": await db.sched_get("auto_check_enabled", False),
            "daily_report": await db.sched_get("daily_report_enabled", False),
            "auto_backup": await db.sched_get("auto_backup_enabled", False),
        }

        # Country breakdown
        country_data = {}
        for folder, phones in all_sessions.items():
            flag, name = get_country_display(folder)
            country_data[folder] = {
                "flag": flag, "name": name, "count": len(phones),
            }

        return templates.TemplateResponse(request, "dashboard.html", {
            "total_sessions": total,
            "countries": countries,
            "spam_counts": spam_counts,
            "contact_counts": contact_counts,
            "admins": admins,
            "country_data": country_data,
            "recent_logs": recent_logs,
            "sched_info": sched_info,
        })

    # ══════════════════════════════════════════════════════════════════════
    #  INCLUDE API ROUTERS
    # ══════════════════════════════════════════════════════════════════════

    from web.routes.sessions import router as sessions_router
    from web.routes.admins import router as admins_router
    from web.routes.settings import router as settings_router
    from web.routes.scheduler import router as scheduler_router

    app.include_router(sessions_router)
    app.include_router(admins_router)
    app.include_router(settings_router)
    app.include_router(scheduler_router)

    return app


app = create_app()
