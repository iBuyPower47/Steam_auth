from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def decode_jwt_expiry(token: str | None) -> float | None:
    """解析 JWT 的过期时间。 / Decode the exp timestamp from a JWT token when available."""
    if not token or "." not in token:
        return None

    parts = token.split(".")
    if len(parts) < 2:
        return None

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None

    exp = data.get("exp")
    if exp is None:
        return None

    try:
        return float(exp)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class CookieData:
    name: str
    value: str
    domain: str = ""
    path: str = "/"
    secure: bool = False
    expires: int | None = None
    rest: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化 Cookie 数据。 / Serialize cookie data into a plain dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
            "secure": self.secure,
            "expires": self.expires,
            "rest": dict(self.rest),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CookieData":
        """反序列化 Cookie 数据。 / Create a CookieData instance from a dictionary."""
        return cls(
            name=str(data["name"]),
            value=str(data["value"]),
            domain=str(data.get("domain") or ""),
            path=str(data.get("path") or "/"),
            secure=bool(data.get("secure", False)),
            expires=data.get("expires"),
            rest=dict(data.get("rest") or {}),
        )


@dataclass(slots=True)
class SessionData:
    username: str
    steamid: str
    refresh_token: str | None = None
    refresh_token_expires_at: float | None = None
    access_token: str | None = None
    access_token_expires_at: float | None = None
    cookies: list[CookieData] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化会话数据。 / Serialize the stored Steam session payload."""
        return {
            "username": self.username,
            "steamid": self.steamid,
            "refresh_token": self.refresh_token,
            "refresh_token_expires_at": self.refresh_token_expires_at,
            "access_token": self.access_token,
            "access_token_expires_at": self.access_token_expires_at,
            "cookies": [cookie.to_dict() for cookie in self.cookies],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionData":
        """反序列化会话数据。 / Create SessionData from stored session payload."""
        cookies = [CookieData.from_dict(item) for item in data.get("cookies", [])]
        return cls(
            username=str(data["username"]),
            steamid=str(data["steamid"]),
            refresh_token=data.get("refresh_token"),
            refresh_token_expires_at=data.get("refresh_token_expires_at")
            or decode_jwt_expiry(data.get("refresh_token")),
            access_token=data.get("access_token"),
            access_token_expires_at=data.get("access_token_expires_at")
            or decode_jwt_expiry(data.get("access_token")),
            cookies=cookies,
        )


@dataclass(slots=True)
class SteamCredentials:
    username: str
    password: str | None = None
    mafile_path: str | Path | None = None
    steamid: str | None = None

    def __post_init__(self) -> None:
        """标准化凭证字段。 / Normalize credential fields after dataclass initialization."""
        if not self.username:
            raise ValueError("username is required")
        if self.mafile_path is not None:
            self.mafile_path = Path(self.mafile_path)
        if self.steamid is not None:
            self.steamid = str(self.steamid)

    @property
    def steam_guard_path(self) -> str | None:
        """返回 steampy 可接受的令牌路径。 / Return the Steam Guard path in steampy-compatible format."""
        if self.mafile_path is None:
            return None
        return str(self.mafile_path)


@dataclass(slots=True)
class SteamLoginOptions:
    proxies: dict[str, str] | None = None
    verify_ssl: bool = True
    max_retries: int = 3
    initial_retry_delay: float = 1.0
    retry_backoff: float = 2.0
    store_key: str | None = None

    def __post_init__(self) -> None:
        """校验登录选项。 / Validate login option values after initialization."""
        if self.max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        if self.initial_retry_delay < 0:
            raise ValueError("initial_retry_delay must be >= 0")
        if self.retry_backoff < 1:
            raise ValueError("retry_backoff must be >= 1")


@dataclass(slots=True)
class LoginResult:
    success: bool
    method: str = "none"
    tried: bool = False
    error: str | None = None
    attempts: int = 0
    username: str | None = None
    steamid: str | None = None
