from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional
import msal
import os
import time
import jwt
from urllib.parse import urlencode

from app.config.settings import (
    get_azure_client_id,
    get_azure_tenant_id,
    get_azure_client_secret,
    get_auth_redirect_uri,
    get_frontend_base_url,
    get_jwt_secret,
    get_jwt_expires_seconds,
)


router = APIRouter(prefix="/auth", tags=["Auth"])


def _build_msal_app():
    client_id = get_azure_client_id()
    client_secret = get_azure_client_secret()
    tenant_id = get_azure_tenant_id()
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    return msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )


def _auth_scopes():
    """Scopes for the authorize request (OIDC + basic Graph)."""
    # Avoid 'email' which can trigger reserved scope errors. Graph provides email in profile.
    return ["openid", "profile", "offline_access", "User.Read"]


def _token_scopes():
    """Scopes for the token request (must NOT include reserved OIDC scopes)."""
    return ["User.Read"]


@router.get("/login")
def login(next: Optional[str] = None):
    """Initiates Azure AD login and redirects to the consent page.

    Builds the authorize URL manually to avoid server errors
    when client secret is not yet configured.
    """
    tenant_id = get_azure_tenant_id()
    client_id = get_azure_client_id()
    redirect_uri = get_auth_redirect_uri()
    if not tenant_id or not client_id:
        raise HTTPException(status_code=500, detail="Azure AD no configurado: falta CLIENT_ID o TENANT_ID")
    if not redirect_uri:
        raise HTTPException(status_code=500, detail="Falta AUTH_REDIRECT_URI en configuración")

    base = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(_auth_scopes()),
        "state": next or get_frontend_base_url(),
        "prompt": "select_account",
    }
    url = f"{base}?{urlencode(params)}"
    return RedirectResponse(url=url)


@router.get("/callback")
def auth_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None):
    """Callback handler: exchanges the auth code for tokens and issues a local JWT."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # Validate secret present for token exchange
    if not get_azure_client_secret():
        raise HTTPException(status_code=500, detail="Azure AD no configurado: falta CLIENT_SECRET para canje de token")

    app = _build_msal_app()
    redirect_uri = get_auth_redirect_uri()
    try:
        result = app.acquire_token_by_authorization_code(
            code=code,
            scopes=_token_scopes(),
            redirect_uri=redirect_uri,
        )
    except Exception as e:
        # Error típico: redirect_uri no coincide o secreto inválido
        raise HTTPException(status_code=400, detail=f"Fallo al canjear el código en Azure AD: {e}")

    if "error" in result:
        err = result.get('error')
        desc = result.get('error_description')
        corr = result.get('correlation_id')
        raise HTTPException(status_code=400, detail=f"Azure AD: {err} - {desc} (correlation_id={corr})")

    claims = result.get("id_token_claims") or {}
    now = int(time.time())
    payload = {
        "sub": claims.get("sub") or claims.get("oid"),
        "name": claims.get("name"),
        "preferred_username": claims.get("preferred_username") or claims.get("email"),
        "oid": claims.get("oid"),
        "tid": claims.get("tid"),
        "iss": "local",
        "iat": now,
        "exp": now + int(get_jwt_expires_seconds()),
    }
    token = jwt.encode(payload, get_jwt_secret(), algorithm="HS256")

    # Redirect back to frontend with token as a query param.
    # Compute frontend return URL; avoid duplicating /auth/return if already present in state
    frontend_base = (state or get_frontend_base_url()).rstrip("/")
    if frontend_base.lower().endswith("/auth/return"):
        final_return = frontend_base
    else:
        final_return = f"{frontend_base}/auth/return"
    url = f"{final_return}?{urlencode({'token': token})}"
    return RedirectResponse(url=url)


@router.get("/me")
def me(authorization: Optional[str] = Header(default=None)):
    """Returns the current user decoded from Authorization: Bearer <jwt>."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        data = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])  # type: ignore
        return {"user": data}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.get("/logout")
def logout():
    tenant = get_azure_tenant_id()
    post_logout = get_frontend_base_url()
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/logout?{urlencode({'post_logout_redirect_uri': post_logout})}"
    return RedirectResponse(url=url)


@router.get("/debug")
def auth_debug():
    """Quick diagnostics for Azure AD config (does not expose secrets)."""
    return {
        "client_id": bool(get_azure_client_id()),
        "tenant_id": get_azure_tenant_id(),
        "redirect_uri": get_auth_redirect_uri(),
        "frontend_base": get_frontend_base_url(),
        "has_client_secret": bool(get_azure_client_secret()),
    }
