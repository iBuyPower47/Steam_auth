from __future__ import annotations

import time
from typing import Any

from steampy.client import SteamClient

from .exceptions import SteamLoginError
from .facade import SteamAuthService
from .models import LoginResult, SteamCredentials, SteamLoginOptions, decode_jwt_expiry
from .store import SessionStore


class SteamAccountClient:
    def __init__(
        self,
        credentials: SteamCredentials,
        session_store: SessionStore | None = None,
        options: SteamLoginOptions | None = None,
        logger: Any | None = None,
    ) -> None:
        """初始化单账号客户端包装器。 / Initialize a single-account client wrapper."""
        self.credentials = credentials
        self.session_store = session_store
        self.options = options or SteamLoginOptions()
        self.logger = logger
        self._client: SteamClient | None = None
        self._status = "offline"
        self._last_login_result = LoginResult(success=False, username=credentials.username)

    @property
    def client(self) -> SteamClient | None:
        """返回底层客户端。 / Return the underlying Steam client instance."""
        return self._client

    @property
    def status(self) -> str:
        """返回当前状态字符串。 / Return the current account status string."""
        return self._status

    @property
    def username(self) -> str:
        """返回用户名。 / Return the Steam username."""
        return self.credentials.username

    @property
    def steamid(self) -> str | None:
        """返回当前 steamid。 / Return the latest known steamid for this account."""
        return self._last_login_result.steamid or self.credentials.steamid

    @property
    def last_login_result(self) -> LoginResult:
        """返回最近一次登录结果。 / Return the latest login result."""
        return self._last_login_result

    def login(self) -> LoginResult:
        """执行登录并更新本地状态。 / Perform login and refresh the local client state."""
        service = SteamAuthService(
            credentials=self.credentials,
            session_store=self.session_store,
            options=self.options,
            logger=self.logger,
        )
        client, result = service.login()
        self._client = client
        self._last_login_result = result
        self._status = "online" if result.success else "error"
        return result

    def ensure_client(self) -> SteamClient:
        """确保存在可用客户端。 / Ensure a usable client exists, logging in only when needed."""
        if self._client is not None and self.has_usable_access_token():
            self._status = "online"
            return self._client

        result = self.login()
        if not result.success or self._client is None:
            raise SteamLoginError(result.error or "Steam login failed")
        return self._client

    def has_usable_access_token(self, skew_seconds: float = 60.0) -> bool:
        """基于本地 token 判断是否可用。 / Check token usability locally based on access token expiry."""
        if self._client is None:
            self._status = "offline"
            return False

        access_token = getattr(self._client, "_access_token", None)
        expires_at = decode_jwt_expiry(access_token)
        if expires_at is None:
            self._status = "offline"
            return False

        usable = expires_at > time.time() + skew_seconds
        self._status = "online" if usable else "offline"
        return usable

    def check_session(self) -> bool:
        """主动探测 Steam 在线会话。 / Probe the remote Steam session state explicitly."""
        if self._client is None:
            self._status = "offline"
            return False

        alive = self._client.is_session_alive()
        self._status = "online" if alive else "offline"
        return alive

    def to_dict(self) -> dict[str, Any]:
        """导出账号摘要。 / Export account summary data for UI or logging."""
        return {
            "username": self.credentials.username,
            "steamid": self._last_login_result.steamid or self.credentials.steamid,
            "status": self._status,
            "last_login_method": self._last_login_result.method,
            "last_error": self._last_login_result.error,
        }
