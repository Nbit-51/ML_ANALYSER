"""Request boundary: browser origin checks, bounded uploads and account isolation."""

from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ml_analyser.core.auth import AuthStore, account_settings
from ml_analyser.core.config import get_settings, request_settings

MAX_REQUEST_BYTES = 30 * 1024 * 1024


class AccessMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        settings = get_settings()
        allowed_hosts = {
            "127.0.0.1",
            "localhost",
            "::1",
            "testserver",
            urlsplit(settings.app_url).hostname,
        }
        if request.url.hostname not in allowed_hosts:
            await JSONResponse({"detail": "Unrecognized host."}, 400)(scope, receive, send)
            return
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            allowed_origins = {str(request.base_url).rstrip("/"), settings.app_url.rstrip("/")}
            if (origin and origin not in allowed_origins) or request.headers.get(
                "sec-fetch-site"
            ) == "cross-site":
                await JSONResponse({"detail": "Cross-site request denied."}, 403)(
                    scope, receive, send
                )
                return
        protected = request.url.path == "/app" or request.url.path.startswith(
            (settings.api_v1_prefix + "/runs", settings.api_v1_prefix + "/repositories")
        )
        scoped = settings
        if settings.auth_enabled and protected:
            user = AuthStore(settings.auth_database).user(request.cookies.get("ml_session", ""))
            allowed = {item.strip().casefold() for item in settings.github_allowed_users.split(",")}
            if not settings.auth_ready or not user or user["login"].casefold() not in allowed:
                response = (
                    RedirectResponse("/login", status_code=303)
                    if request.url.path == "/app"
                    else JSONResponse({"detail": "Sign in to continue."}, 401)
                )
                await response(scope, receive, send)
                return
            scoped = account_settings(settings, user["id"])
        # Bound bytes before JSON parsing, including chunked bodies without Content-Length.
        messages: list[Message] = []
        size = 0
        if request.method in {"POST", "PUT", "PATCH"}:
            while True:
                message = await receive()
                messages.append(message)
                size += len(message.get("body", b""))
                if size > MAX_REQUEST_BYTES:
                    await JSONResponse({"detail": "Upload exceeds 30 MB."}, 413)(
                        scope, receive, send
                    )
                    return
                if not message.get("more_body", False):
                    break

        async def bounded_receive() -> Message:
            return messages.pop(0) if messages else await receive()

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                    ]
                )
                message["headers"] = headers
            await send(message)

        token = request_settings.set(scoped)
        try:
            await self.app(scope, bounded_receive, secure_send)
        finally:
            request_settings.reset(token)
