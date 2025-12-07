"""Helper utilities for interacting with the Angel One SmartAPI."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional
from uuid import uuid4

import requests
from django.conf import settings


class AngelAPIError(RuntimeError):
    """Raised when the Angel API returns an error or cannot be reached."""


def _coerce_timeout() -> float:
    try:
        return float(getattr(settings, "ANGEL_API_TIMEOUT", 30))
    except (TypeError, ValueError):
        return 30.0


def build_headers(*, api_key: str, bearer_token: Optional[str] = None) -> Dict[str, str]:
    if not api_key:
        raise AngelAPIError("API key is required to contact Angel API")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": getattr(settings, "ANGEL_USER_TYPE", "USER"),
        "X-SourceID": getattr(settings, "ANGEL_SOURCE_ID", "WEB"),
        "X-ClientLocalIP": getattr(settings, "ANGEL_CLIENT_LOCAL_IP", "127.0.0.1"),
        "X-ClientPublicIP": getattr(settings, "ANGEL_CLIENT_PUBLIC_IP", "106.193.147.98"),
        "X-MACAddress": getattr(settings, "ANGEL_CLIENT_MAC", "00:00:00:00:00:00"),
        "X-PrivateKey": api_key,
    }

    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    return headers


def _request(
    method: str,
    url: str,
    *,
    api_key: str,
    bearer_token: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    headers = build_headers(api_key=api_key, bearer_token=bearer_token)
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=payload,
            timeout=_coerce_timeout(),
        )
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network failure case
        raise AngelAPIError(str(exc)) from exc

    try:
        data: Dict[str, Any] = response.json()
    except json.JSONDecodeError as exc:  # pragma: no cover - unexpected response
        raise AngelAPIError("Invalid JSON received from Angel API") from exc

    return data


def _url(name: str, default: str) -> str:
    return getattr(settings, name, default)


def login(*, api_key: str, clientcode: str, password: str, totp: str) -> Dict[str, Any]:
    payload = {
        "clientcode": clientcode,
        "password": password,
        "totp": totp,
    }
    data = _request(
        "POST",
        _url(
            "ANGEL_API_LOGIN_URL",
            "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword",
        ),
        api_key=api_key,
        payload=payload,
    )

    if not data.get("status"):
        raise AngelAPIError(data.get("message") or "Login failed")
    return data


def get_profile(*, api_key: str, jwt_token: str) -> Dict[str, Any]:
    return _request(
        "GET",
        _url(
            "ANGEL_API_PROFILE_URL",
            "https://apiconnect.angelone.in/rest/secure/angelbroking/user/v1/getProfile",
        ),
        api_key=api_key,
        bearer_token=jwt_token,
    )


def refresh_tokens(*, api_key: str, jwt_token: str, refresh_token: str) -> Dict[str, Any]:
    payload = {
        "refreshToken": refresh_token,
        "jwtToken": jwt_token,
    }
    data = _request(
        "POST",
        _url(
            "ANGEL_API_TOKEN_URL",
            "https://apiconnect.angelone.in/rest/auth/angelbroking/jwt/v1/generateTokens",
        ),
        api_key=api_key,
        bearer_token=jwt_token,
        payload=payload,
    )

    if not data.get("status"):
        raise AngelAPIError(data.get("message") or "Token refresh failed")
    return data


def place_order(
    *,
    api_key: str,
    jwt_token: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    if getattr(settings, "ANGEL_SANDBOX_ENABLED", False):
        quantity = payload.get("quantity") or "0"
        return {
            "status": True,
            "message": "Sandbox order accepted",
            "data": {
                "orderid": f"SBX{uuid4().hex[:12].upper()}",
                "filledqty": quantity,
            },
        }

    data = _request(
        "POST",
        _url(
            "ANGEL_API_PLACE_ORDER_URL",
            "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder",
        ),
        api_key=api_key,
        bearer_token=jwt_token,
        payload=payload,
    )

    if not data.get("status"):
        raise AngelAPIError(data.get("message") or "Order placement failed")
    return data
