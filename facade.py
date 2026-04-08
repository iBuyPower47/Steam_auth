from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from steampy.client import SteamClient

from .exceptions import DependencyUnavailableError, SteamLoginError
from .login_coordinator import LoginCoordinator, create_client
from .models import LoginResult, SteamCredentials, SteamLoginOptions
from .store import EncryptedFileStore, JsonFileStore, SessionStore


def build_default_session_store(
    data_dir: str | Path,
    allow_plaintext_fallback: bool = False,
) -> SessionStore:
    """构建默认会话存储。 / Build the default session store with encrypted storage when available."""
    try:
        from cryptography.fernet import Fernet  # noqa: F401
        return EncryptedFileStore(data_dir=data_dir)
    except (DependencyUnavailableError, ImportError):
        if not allow_plaintext_fallback:
            raise
        return JsonFileStore(Path(data_dir) / "sessions.json")


class SteamAuthService:
    def __init__(
        self,
        credentials: SteamCredentials,
        session_store: SessionStore | None = None,
        options: SteamLoginOptions | None = None,
        logger: Any | None = None,
        client_factory: Callable[[SteamCredentials, SteamLoginOptions], SteamClient] | None = None,
    ) -> None:
        """初始化认证服务。 / Initialize the auth service wrapper around the login coordinator."""
        self.credentials = credentials
        self.session_store = session_store
        self.options = options or SteamLoginOptions()
        self.logger = logger
        self.client_factory = client_factory or create_client

    def login(self) -> tuple[SteamClient, LoginResult]:
        """执行一次完整登录尝试。 / Execute a full login attempt and return the client plus result."""
        client = self.client_factory(self.credentials, self.options)
        coordinator = LoginCoordinator(
            client=client,
            credentials=self.credentials,
            session_store=self.session_store,
            options=self.options,
            logger=self.logger,
        )
        result = coordinator.login()
        return client, result

    def login_or_raise(self) -> SteamClient:
        """登录失败时抛出异常。 / Log in and raise an exception if the attempt fails."""
        client, result = self.login()
        if not result.success:
            raise SteamLoginError(result.error or "Steam login failed")
        return client


def login_and_get_client(
    username: str,
    password: str | None,
    mafile_path: str | Path | None = None,
    steamid: str | None = None,
    data_dir: str | Path | None = None,
    proxies: dict[str, str] | None = None,
    verify_ssl: bool = True,
    max_retries: int = 3,
    logger: Any | None = None,
    session_store: SessionStore | None = None,
    allow_plaintext_fallback: bool = False,
) -> tuple[SteamClient, LoginResult]:
    """按参数快速完成登录。 / Convenience helper that logs in with explicit function arguments."""
    credentials = SteamCredentials(
        username=username,
        password=password,
        mafile_path=mafile_path,
        steamid=steamid,
    )
    options = SteamLoginOptions(
        proxies=proxies,
        verify_ssl=verify_ssl,
        max_retries=max_retries,
    )

    if session_store is None and data_dir is not None:
        session_store = build_default_session_store(
            data_dir=data_dir,
            allow_plaintext_fallback=allow_plaintext_fallback,
        )

    service = SteamAuthService(
        credentials=credentials,
        session_store=session_store,
        options=options,
        logger=logger,
    )
    return service.login()
