from __future__ import annotations

import os
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.integration_store import (
    create_oauth_state,
    consume_oauth_state,
    delete_connection,
    get_connection,
    save_connection,
)

router = APIRouter(
    prefix="/integrations/google",
    tags=["Google OAuth"],
)

# Use canonical scope URLs consistently.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.readonly",
]

GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise HTTPException(
            status_code=500,
            detail=f"Missing required environment variable: {name}",
        )

    return value


def _config() -> dict:
    client_id = _required_env("GOOGLE_CLIENT_ID")
    client_secret = _required_env("GOOGLE_CLIENT_SECRET")
    redirect_uri = _required_env("GOOGLE_REDIRECT_URI")

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def _create_flow() -> Flow:
    return Flow.from_client_config(
        _config(),
        scopes=SCOPES,
        redirect_uri=_required_env("GOOGLE_REDIRECT_URI"),
    )


@router.get("/connect")
def connect(user_id: str = Query(..., min_length=1)):
    """
    Start the Google OAuth flow.

    The browser user id is never used directly as OAuth state. A random, expiring,
    single-use server-side state token protects the callback from CSRF/replay.
    """
    flow = _create_flow()
    oauth_state = create_oauth_state(user_id, "google")

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        # Always surface the account chooser during team testing so switching
        # Gmail accounts cannot silently reuse the browser's previous account.
        prompt="consent select_account",
        state=oauth_state,
    )

    return RedirectResponse(
        url=authorization_url,
        status_code=307,
    )


@router.get("/callback")
def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    """
    Complete Google authorization, validate Gmail permission,
    and save the encrypted account connection.
    """

    if error:
        raise HTTPException(
            status_code=400,
            detail={
                "error": error,
                "message": error_description or "Google authorization was denied.",
            },
        )

    if not code or not state:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth callback is missing code or state.",
        )

    try:
        user_id = consume_oauth_state(state, "google")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Google OAuth state is invalid or expired. Please reconnect Gmail.") from exc

    flow = _create_flow()

    # Google can normalize equivalent identity scopes in its token response.
    # This permits token parsing, after which we independently enforce the
    # required Gmail permission below.
    previous_relax_setting = os.environ.get("OAUTHLIB_RELAX_TOKEN_SCOPE")
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "google_token_exchange_failed",
                "message": str(exc),
            },
        ) from exc
    finally:
        if previous_relax_setting is None:
            os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
        else:
            os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = previous_relax_setting

    credentials = flow.credentials
    granted_scopes = set(credentials.scopes or [])

    if GMAIL_READ_SCOPE not in granted_scopes:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "gmail_permission_missing",
                "message": (
                    "Google signed in successfully, but Gmail read permission "
                    "was not granted. Remove the existing Email-AI connection "
                    "from your Google Account and reconnect."
                ),
                "granted_scopes": sorted(granted_scopes),
                "required_scope": GMAIL_READ_SCOPE,
            },
        )

    try:
        oauth_service = build(
            "oauth2",
            "v2",
            credentials=credentials,
            cache_discovery=False,
        )

        user_info = (
            oauth_service
            .userinfo()
            .get()
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "google_profile_lookup_failed",
                "message": str(exc),
            },
        ) from exc

    account_email = user_info.get("email", "").strip()

    if not account_email:
        raise HTTPException(
            status_code=400,
            detail="Google did not return an account email address.",
        )

    save_connection(
        user_id,
        "google",
        account_email,
        {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": sorted(granted_scopes),
            "expiry": (
                credentials.expiry.isoformat()
                if credentials.expiry
                else None
            ),
        },
        sorted(granted_scopes),
    )

    frontend_url = os.getenv(
        "FRONTEND_URL",
        "http://127.0.0.1:5173",
    ).rstrip("/")

    query = urlencode(
        {
            "gmail": "connected",
            "email": account_email,
            # Return the opaque workspace id that initiated this OAuth flow.
            # The frontend makes it the active account context after callback.
            "user_id": user_id,
        }
    )

    return RedirectResponse(
        url=f"{frontend_url}?{query}",
        status_code=307,
    )


@router.get("/status")
def status(user_id: str = Query(..., min_length=1)):
    connection = get_connection(user_id, "google")

    return {
        "connected": bool(connection),
        "email": (
            connection.get("account_email")
            if connection
            else None
        ),
    }


@router.delete("")
def disconnect(user_id: str = Query(..., min_length=1)):
    delete_connection(user_id, "google")

    return {
        "connected": False,
        "email": None,
    }