"""GitHub OAuth authorization-code flow with state, PKCE and revocable sessions."""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ml_analyser.core.auth import AuthStore, account_settings, seed_demos
from ml_analyser.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/status")
def auth_status(request: Request) -> dict[str, object]:
    settings = get_settings()
    user = AuthStore(settings.auth_database).user(request.cookies.get("ml_session", ""))
    return {
        "enabled": settings.auth_enabled,
        "configured": settings.auth_ready,
        "user": user,
        "provider": settings.model_provider,
        "callback_url": settings.app_url.rstrip("/") + "/api/v1/auth/callback",
    }


@router.get("/github")
def github_login() -> RedirectResponse:
    settings = get_settings()
    if not settings.auth_ready:
        return RedirectResponse("/login?setup=required", status_code=303)
    state, verifier = AuthStore(settings.auth_database).begin()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.app_url.rstrip("/") + "/api/v1/auth/callback",
            "state": state,
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
        }
    )
    response = RedirectResponse(
        "https://github.com/login/oauth/authorize?" + query, status_code=303
    )
    response.set_cookie(
        "ml_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings.app_url.startswith("https://"),
        samesite="lax",
        path="/api/v1/auth",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


async def github_identity(code: str, verifier: str) -> dict[str, object]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret.get_secret_value(),
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": settings.app_url.rstrip("/") + "/api/v1/auth/callback",
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("Token exchange failed")
        identity = await client.get(
            "https://api.github.com/user", headers={"Authorization": f"Bearer {token}"}
        )
        identity.raise_for_status()
        body: dict[str, object] = identity.json()
        return body


@router.get("/callback")
async def github_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    settings = get_settings()
    store = AuthStore(settings.auth_database)
    if (
        not settings.auth_ready
        or not state
        or not secrets.compare_digest(state, request.cookies.get("ml_oauth_state", ""))
    ):
        raise HTTPException(400, "Sign-in expired or invalid. Start again from the sign-in page.")
    verifier = store.consume(state)
    if not verifier or not code:
        raise HTTPException(400, "Sign-in expired or cancelled. Please try again.")
    try:
        identity = await github_identity(code, verifier)
        user_id, login = str(identity["id"]), str(identity["login"])
        allowed = {value.strip().casefold() for value in settings.github_allowed_users.split(",")}
        if login.casefold() not in allowed:
            raise HTTPException(403, "This account is not allowed on this installation.")
        seed_demos(account_settings(settings, user_id))
    except (httpx.HTTPError, ValueError, KeyError) as error:
        raise HTTPException(
            502, "GitHub sign-in could not be completed. Please try again."
        ) from error
    # Access token is deliberately not stored; login requests no private-repository scopes.
    token = store.create(user_id, login)
    store.revoke(request.cookies.get("ml_session", ""))
    response = RedirectResponse("/app", status_code=303)
    response.delete_cookie("ml_oauth_state", path="/api/v1/auth")
    response.set_cookie(
        "ml_session",
        token,
        max_age=28800,
        httponly=True,
        secure=settings.app_url.startswith("https://"),
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    AuthStore(get_settings().auth_database).revoke(request.cookies.get("ml_session", ""))
    response = RedirectResponse("/login?logged_out=1", status_code=303)
    response.delete_cookie("ml_session")
    response.headers["Cache-Control"] = "no-store"
    return response
