from __future__ import annotations

import base64
import os
import time
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.integration_store import (
    create_oauth_state,
    consume_oauth_state,
    delete_connection,
    get_connection,
    save_connection,
)

router = APIRouter(
    prefix="/integrations/yahoo",
    tags=["Yahoo OAuth"],
)

YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
YAHOO_USERINFO_URL = "https://api.login.yahoo.com/openid/v1/userinfo"

# mail-r is a restricted Yahoo scope. Yahoo must enable Mail API access
# for the developer application before mailbox reads can work.
YAHOO_SCOPES = ["openid", "profile", "email", "mail-r"]


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(status_code=503, detail=f"{name} is required for Yahoo OAuth.")
    return value


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "").strip() or "http://localhost:5173"


def _client_auth_header() -> str:
    raw = f"{_required_env('YAHOO_CLIENT_ID')}:{_required_env('YAHOO_CLIENT_SECRET')}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _exchange_code(code: str) -> dict:
    response = requests.post(
        YAHOO_TOKEN_URL,
        headers={
            "Authorization": _client_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "redirect_uri": _required_env("YAHOO_REDIRECT_URI"),
            "code": code,
        },
        timeout=30,
    )
    if not response.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "yahoo_token_exchange_failed",
                "status": response.status_code,
                "message": response.text[:1200],
            },
        )
    return response.json()


def refresh_yahoo_access_token(user_id: str) -> str:
    connection = get_connection(user_id, "yahoo")
    if not connection:
        raise RuntimeError("Yahoo is not connected for this workspace.")

    credentials = connection.get("credentials") or {}
    access_token = str(credentials.get("access_token") or "")
    expires_at = int(credentials.get("expires_at") or 0)

    if access_token and expires_at > int(time.time()) + 60:
        return access_token

    refresh_token = str(credentials.get("refresh_token") or "")
    if not refresh_token:
        raise RuntimeError("Yahoo refresh token is missing. Reconnect Yahoo.")

    response = requests.post(
        YAHOO_TOKEN_URL,
        headers={
            "Authorization": _client_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "redirect_uri": _required_env("YAHOO_REDIRECT_URI"),
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Yahoo token refresh failed: {response.status_code} {response.text[:500]}")

    token = response.json()
    new_refresh = token.get("refresh_token") or refresh_token
    updated = {
        **credentials,
        "access_token": token.get("access_token") or "",
        "refresh_token": new_refresh,
        "token_type": token.get("token_type") or "bearer",
        "expires_at": int(time.time()) + int(token.get("expires_in") or 3600),
    }
    save_connection(
        user_id,
        "yahoo",
        connection.get("account_email") or "",
        updated,
        connection.get("scopes") or YAHOO_SCOPES,
    )
    return str(updated["access_token"])


@router.get("/connect")
def connect(user_id: str = Query(..., min_length=1)):
    state = create_oauth_state(user_id, "yahoo")
    params = {
        "client_id": _required_env("YAHOO_CLIENT_ID"),
        "redirect_uri": _required_env("YAHOO_REDIRECT_URI"),
        "response_type": "code",
        "scope": " ".join(YAHOO_SCOPES),
        "state": state,
    }
    return RedirectResponse(f"{YAHOO_AUTH_URL}?{urlencode(params)}")


@router.get("/callback")
def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    if error:
        params = urlencode({
            "yahoo": "error",
            "message": error_description or error,
        })
        return RedirectResponse(f"{_frontend_url()}?{params}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Yahoo OAuth callback is missing code or state.")

    try:
        user_id = consume_oauth_state(state, "yahoo")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Yahoo OAuth state is invalid or expired. Please reconnect Yahoo.",
        ) from exc

    token = _exchange_code(code)
    access_token = str(token.get("access_token") or "")
    if not access_token:
        raise HTTPException(status_code=400, detail="Yahoo did not return an access token.")

    profile_response = requests.get(
        YAHOO_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if not profile_response.ok:
        raise HTTPException(
            status_code=400,
            detail=f"Yahoo profile lookup failed: {profile_response.status_code}",
        )

    profile = profile_response.json()
    account_email = str(profile.get("email") or "").strip().lower()
    if not account_email:
        raise HTTPException(status_code=400, detail="Yahoo did not return an account email address.")

    granted_scope = token.get("scope")
    if isinstance(granted_scope, str):
        granted_scopes = [x for x in granted_scope.replace(",", " ").split() if x]
    else:
        granted_scopes = list(YAHOO_SCOPES)

    credentials = {
        "access_token": access_token,
        "refresh_token": token.get("refresh_token") or "",
        "token_type": token.get("token_type") or "bearer",
        "expires_at": int(time.time()) + int(token.get("expires_in") or 3600),
        "xoauth_yahoo_guid": token.get("xoauth_yahoo_guid") or "",
    }

    save_connection(
        user_id,
        "yahoo",
        account_email,
        credentials,
        granted_scopes,
    )

    params = urlencode({
        "yahoo": "connected",
        "email": account_email,
        "user_id": user_id,
    })
    return RedirectResponse(f"{_frontend_url()}?{params}")


@router.get("/status")
def status(user_id: str = Query(..., min_length=1)):
    connection = get_connection(user_id, "yahoo")
    scopes = connection.get("scopes") if connection else []
    return {
        "connected": bool(connection),
        "email": connection.get("account_email") if connection else "",
        "mail_scope_requested": "mail-r" in (scopes or []),
        "scopes": scopes or [],
    }


@router.delete("")
def disconnect(user_id: str = Query(..., min_length=1)):
    delete_connection(user_id, "yahoo")
    return {"connected": False, "provider": "yahoo"}
