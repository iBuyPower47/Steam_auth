from __future__ import annotations

import time
from typing import Any
from urllib.parse import unquote

import requests
from steampy.client import SteamClient
from steampy.exceptions import ApiException, InvalidCredentials

from .models import (
    CookieData,
    LoginResult,
    SessionData,
    SteamCredentials,
    SteamLoginOptions,
    decode_jwt_expiry,
)
from .store import SessionStore, SessionStoreError


class LoginCoordinator:
    def __init__(
        self,
        client: SteamClient,
        credentials: SteamCredentials,
        session_store: SessionStore | None = None,
        options: SteamLoginOptions | None = None,
        logger: Any | None = None,
    ) -> None:
        """初始化登录协调器。 / Initialize the coordinator that orchestrates Steam login strategies."""
        self.client = client
        self.credentials = credentials
        self.session_store = session_store
        self.options = options or SteamLoginOptions()
        self.logger = logger
        self._configure_client()

    def login(self) -> LoginResult:
        """按恢复优先级执行登录。 / Run the login flow with restore-first strategy ordering."""
        last_error: str | None = None
        for attempt in (self._try_cookie_restore, self._try_token_login, self._try_password_login):
            result = attempt()
            if result.success:
                self.credentials.steamid = result.steamid or self.credentials.steamid
                return result
            if result.tried and result.error:
                last_error = result.error

        return LoginResult(
            success=False,
            method="none",
            tried=True,
            error=last_error or "Steam login failed",
            attempts=self.options.max_retries,
            username=self.credentials.username,
            steamid=self._current_steamid(),
        )

    def _configure_client(self) -> None:
        """应用客户端网络配置。 / Apply network and SSL settings to the Steam client."""
        self.client._session.verify = self.options.verify_ssl
        if self.options.proxies:
            self.client.set_proxies(self.options.proxies)

    def _try_cookie_restore(self) -> LoginResult:
        """尝试通过 cookies 恢复会话。 / Attempt to restore a session from stored cookies and tokens."""
        session = self._get_stored_session()
        if session is None or not session.cookies:
            return self._result(False, method="cookie", tried=False)

        refresh_expired = self._is_token_expired(session.refresh_token_expires_at)
        access_expired = self._is_token_expired(session.access_token_expires_at)
        access_needs_refresh = self._is_token_near_expiry(session.access_token_expires_at)

        if access_expired and refresh_expired:
            self._delete_stored_session()
            return self._result(
                False,
                method="cookie",
                tried=True,
                error="stored access_token and refresh_token have expired",
            )

        self._log("info", "尝试cookie登录 %s", self.credentials.username)
        try:
            self._restore_session(session)
            if not access_needs_refresh and self.client.is_access_token_valid():
                self._persist_current_session()
                return self._result(True, method="cookie", tried=True)

            if refresh_expired:
                self._delete_stored_session()
                return self._handle_restore_failure("存储的refresh_token已过期")

            if self.client.update_access_token() and self.client.is_access_token_valid():
                self._persist_current_session()
                return self._result(True, method="cookie", tried=True)

            return self._handle_restore_failure("存储的Cookie已失效")
        except Exception as exc:
            return self._handle_restore_failure(str(exc))

    def _try_token_login(self) -> LoginResult:
        """尝试使用 refresh token 登录。 / Attempt login by refresh token when cookie restore is insufficient."""
        session = self._get_stored_session()
        if session is None or not session.refresh_token or not session.steamid:
            return self._result(False, method="token", tried=False)
        if self._is_token_expired(session.refresh_token_expires_at):
            self._delete_stored_session()
            return self._result(False, method="token", tried=False)

        self._log("info", "尝试refresh_token登录 %s", self.credentials.username)
        try:
            succeeded = self.client.login_by_refresh_token(
                refresh_token=session.refresh_token,
                steamid=session.steamid,
                steam_guard=self.credentials.steam_guard_path,
            )
            if not succeeded:
                self._delete_stored_session()
                return self._result(
                    False,
                    method="token",
                    tried=True,
                    error="refresh_token login failed",
                )

            self._mark_client_logged_in(session.steamid)
            self._persist_current_session()
            return self._result(True, method="token", tried=True)
        except Exception as exc:
            self._delete_stored_session()
            return self._result(False, method="token", tried=True, error=str(exc))

    def _try_password_login(self) -> LoginResult:
        """尝试账号密码登录。 / Attempt a password-based login with retry support."""
        if not self.credentials.password:
            return self._result(
                False,
                method="password",
                tried=False,
                error="password is required for password login",
            )
        if not self.credentials.steam_guard_path:
            return self._result(
                False,
                method="password",
                tried=False,
                error="mafile_path is required for password login",
            )

        attempts = 0
        delay = self.options.initial_retry_delay
        last_error: str | None = None
        for index in range(1, self.options.max_retries + 1):
            attempts = index
            try:
                self._log("info", "尝试密码登录 %s (attempt %s)", self.credentials.username, index)
                self.client.login(
                    username=self.credentials.username,
                    password=self.credentials.password,
                    steam_guard=self.credentials.steam_guard_path,
                )
                self._mark_client_logged_in(self._current_steamid())
                self._persist_current_session()
                return self._result(True, method="password", tried=True, attempts=attempts)
            except InvalidCredentials as exc:
                last_error = str(exc) or "invalid credentials"
                break
            except (ApiException, requests.RequestException, ValueError) as exc:
                last_error = str(exc)
                self._log("warning", "Steam密码登录失败 failed for %s: %s", self.credentials.username, last_error)
            except Exception as exc:
                last_error = str(exc)
                self._log("warning", "Steam密码登录失败 failed for %s: %s", self.credentials.username, last_error)

            if index < self.options.max_retries and delay > 0:
                time.sleep(delay)
                delay *= self.options.retry_backoff

        return self._result(
            False,
            method="password",
            tried=True,
            attempts=attempts,
            error=last_error or "password login failed",
        )

    def _get_store_key(self) -> str:
        """返回会话存储键。 / Return the session storage key for the current account."""
        return self.options.store_key or self.credentials.username

    def _get_stored_session(self) -> SessionData | None:
        """读取已保存会话。 / Read the stored session for the current account."""
        if self.session_store is None:
            return None
        try:
            return self.session_store.get(self._get_store_key())
        except SessionStoreError:
            raise
        except Exception as exc:
            raise SessionStoreError("cannot read stored session") from exc

    def _persist_current_session(self) -> None:
        """持久化当前客户端会话。 / Persist the current client session snapshot."""
        if self.session_store is None:
            return
        session = self._capture_session()
        self.session_store.set(session)

    def _delete_stored_session(self) -> None:
        """删除已保存会话。 / Delete the stored session for the current account."""
        if self.session_store is None:
            return
        self.session_store.delete(self._get_store_key())

    def _capture_session(self) -> SessionData:
        """提取当前客户端会话数据。 / Capture the current client session into SessionData."""
        cookies = [
            CookieData(
                name=cookie.name,
                value=cookie.value,
                domain=cookie.domain or "",
                path=cookie.path or "/",
                secure=bool(cookie.secure),
                expires=cookie.expires,
                rest=dict(getattr(cookie, "_rest", {}) or {}),
            )
            for cookie in self.client._session.cookies
        ]
        steamid = self._current_steamid() or ""
        refresh_token = getattr(self.client, "refresh_token", None)
        access_token = getattr(self.client, "_access_token", None) or self._extract_access_token_from_cookies(cookies)
        return SessionData(
            username=self._get_store_key(),
            steamid=steamid,
            refresh_token=refresh_token,
            refresh_token_expires_at=decode_jwt_expiry(refresh_token),
            access_token=access_token,
            access_token_expires_at=decode_jwt_expiry(access_token),
            cookies=cookies,
        )

    def _restore_session(self, session: SessionData) -> None:
        """将存储会话恢复到客户端。 / Restore stored session data back into the Steam client."""
        self.client._session.cookies.clear()
        for cookie in session.cookies:
            params = {
                "name": cookie.name,
                "value": cookie.value,
                "path": cookie.path or "/",
                "secure": cookie.secure,
            }
            if cookie.domain:
                params["domain"] = cookie.domain
            if cookie.expires is not None:
                params["expires"] = cookie.expires
            if cookie.rest:
                params["rest"] = dict(cookie.rest)
            self.client._session.cookies.set(**params)

        self.client.steamid = session.steamid
        self.client.refresh_token = session.refresh_token
        self.client._access_token = session.access_token or self._extract_access_token_from_cookies(session.cookies)
        self._mark_client_logged_in(session.steamid)

    @staticmethod
    def _is_token_expired(expires_at: float | None, skew_seconds: float = 60.0) -> bool:
        """判断 token 是否已过期。 / Determine whether a token should be treated as expired."""
        if expires_at is None:
            return False
        return time.time() >= float(expires_at) - skew_seconds

    @staticmethod
    def _is_token_near_expiry(expires_at: float | None, refresh_window_seconds: float = 300.0) -> bool:
        """判断 token 是否接近过期。 / Determine whether a token is close enough to expiry to refresh."""
        if expires_at is None:
            return False
        return time.time() >= float(expires_at) - refresh_window_seconds

    def _mark_client_logged_in(self, steamid: str | None) -> None:
        """同步 steampy 的已登录状态。 / Mark steampy internals as logged in for follow-up API usage."""
        if steamid:
            self.client.steamid = steamid
        self.client.was_login_executed = True

        if self.client.steam_guard is None and steamid:
            self.client.steam_guard = {"steamid": str(steamid)}

        try:
            session_id = self.client._session.cookies.get_dict(domain="steamcommunity.com").get("sessionid")
            if not session_id:
                session_id = self.client._session.cookies.get("sessionid")
            if session_id:
                self.client.market._set_login_executed(self.client.steam_guard, session_id, self.client.steamid)
        except Exception:
            return

    def _extract_access_token_from_cookies(self, cookies: list[CookieData]) -> str | None:
        """从 cookie 中提取 access token。 / Extract the access token from steamLoginSecure cookies."""
        for cookie in cookies:
            if cookie.name != "steamLoginSecure":
                continue
            decoded = unquote(cookie.value)
            parts = decoded.split("||", 1)
            if len(parts) == 2 and parts[1]:
                return parts[1]
        return None

    def _handle_restore_failure(self, error: str) -> LoginResult:
        """处理恢复失败后的状态。 / Reset client state after restore failure and build a result."""
        self.client._session.cookies.clear()
        self.client.was_login_executed = False
        return self._result(False, method="cookie", tried=True, error=error)

    def _current_steamid(self) -> str | None:
        """返回当前有效 steamid。 / Return the current effective steamid for this login flow."""
        steamid = self.client.steamid or self.credentials.steamid
        return str(steamid) if steamid else None

    def _result(
        self,
        success: bool,
        method: str,
        tried: bool,
        error: str | None = None,
        attempts: int = 0,
    ) -> LoginResult:
        """构造标准登录结果。 / Build a standard LoginResult object."""
        return LoginResult(
            success=success,
            method=method,
            tried=tried,
            error=error,
            attempts=attempts,
            username=self.credentials.username,
            steamid=self._current_steamid(),
        )

    def _log(self, level: str, message: str, *args: Any) -> None:
        """透传日志到外部 logger。 / Forward a log message to the injected logger when available."""
        if self.logger is None:
            return
        log_fn = getattr(self.logger, level, None)
        if callable(log_fn):
            log_fn(message, *args)


def create_client(
    credentials: SteamCredentials,
    options: SteamLoginOptions | None = None,
) -> SteamClient:
    """创建 steampy 客户端。 / Create a configured steampy SteamClient instance."""
    settings = options or SteamLoginOptions()
    return SteamClient(
        username=credentials.username,
        password=credentials.password,
        steam_guard=credentials.steam_guard_path,
        proxies=settings.proxies,
    )
