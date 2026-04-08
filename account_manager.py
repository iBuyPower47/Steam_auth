from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

from .mafile import scan_mafiles
from .models import LoginResult, SteamCredentials, SteamLoginOptions
from .steam_account_client import SteamAccountClient
from .store import SessionStore


def _load_passwords(accounts_file: str | Path) -> dict[str, str]:
    """读取账号密码映射。 / Load the username-to-password mapping from the accounts file."""
    account_path = Path(accounts_file)
    if not account_path.exists():
        raise FileNotFoundError(f"accounts file does not exist: {account_path}")

    result: dict[str, str] = {}
    for raw_line in account_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "----" not in line:
            continue
        username, password = line.split("----", 1)
        result[username.strip()] = password.strip()
    return result


class AccountManager:
    def __init__(
        self,
        session_store: SessionStore | None = None,
        options: SteamLoginOptions | None = None,
        logger: Any | None = None,
    ) -> None:
        """初始化账号管理器。 / Initialize the account manager and shared login dependencies."""
        self.session_store = session_store
        self.options = options or SteamLoginOptions()
        self.logger = logger
        self._accounts: dict[str, SteamAccountClient] = {}

    def add_account(self, credentials: SteamCredentials) -> SteamAccountClient:
        """添加一个 Steam 账号客户端。 / Add a Steam account client to the manager."""
        account = SteamAccountClient(
            credentials=credentials,
            session_store=self.session_store,
            options=self.options,
            logger=self.logger,
        )
        self._accounts[credentials.username] = account
        return account

    def get_account(self, username: str) -> SteamAccountClient | None:
        """按用户名获取账号。 / Get a managed account by username."""
        return self._accounts.get(username)

    def get_accounts(self) -> list[SteamAccountClient]:
        """返回全部账号。 / Return all managed account clients."""
        return list(self._accounts.values())

    def get_steamid_account_map(self) -> dict[str, SteamAccountClient]:
        """建立 steamid 到账号的映射。 / Build a steamid-to-account mapping for routing."""
        result: dict[str, SteamAccountClient] = {}
        for account in self._accounts.values():
            steamid = account.steamid
            if steamid:
                result[str(steamid)] = account
        return result

    def get_all_accounts_data(self) -> list[dict[str, Any]]:
        """导出全部账号摘要。 / Export summary dictionaries for all managed accounts."""
        return [account.to_dict() for account in self._accounts.values()]

    def batch_login(self, delay_range: tuple[float, float] | None = None) -> dict[str, LoginResult]:
        """按顺序批量登录账号。 / Log in all managed accounts sequentially with optional delays."""
        results: dict[str, LoginResult] = {}
        total = len(self._accounts)
        for index, account in enumerate(self._accounts.values(), start=1):
            if self.logger is not None:
                self.logger.info("批量登录 %s/%s: %s", index, total, account.credentials.username)
            results[account.credentials.username] = account.login()
            if delay_range is not None and index < total:
                lower, upper = delay_range
                time.sleep(random.uniform(lower, upper))
        return results

    @classmethod
    def from_sources(
        cls,
        accounts_file: str | Path,
        mafiles_dir: str | Path,
        session_store: SessionStore | None = None,
        options: SteamLoginOptions | None = None,
        logger: Any | None = None,
    ) -> "AccountManager":
        """从账号文件和 mafile 目录构建管理器。 / Build a manager from an accounts file and mafile directory."""
        manager = cls(session_store=session_store, options=options, logger=logger)
        passwords = _load_passwords(accounts_file)
        mafiles = scan_mafiles(mafiles_dir)
        for username, password in passwords.items():
            mafile_path = mafiles.get(username)
            if mafile_path is None:
                continue
            manager.add_account(
                SteamCredentials(
                    username=username,
                    password=password,
                    mafile_path=mafile_path,
                )
            )
        return manager
