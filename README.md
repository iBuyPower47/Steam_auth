# steam_auth

[Chinese](./README.zh-CN.md)

`steam_auth` is a lightweight Steam login orchestration package built for long-running automation services.
It restores sessions from local storage first, refreshes tokens only when needed, and falls back to password login only when the stored session is no longer usable.

## Features

- Cookie restore, refresh-token login, and password login in one flow
- Local access-token expiry checks to avoid unnecessary remote session probing
- Encrypted session persistence with plaintext JSON fallback
- Multi-account loading from `accounts.txt` plus Steam Desktop Authenticator `mafile` files
- Thin account manager for account routing by `steamid`

## Package Layout

```text
steam_auth/
|-- __init__.py
|-- account_manager.py
|-- exceptions.py
|-- facade.py
|-- login_coordinator.py
|-- mafile.py
|-- models.py
|-- steam_account_client.py
|-- store.py
|-- README.md
`-- README.zh-CN.md
```

## Login Strategy

The login flow runs in this order:

1. Restore cookies and tokens from local session storage
2. Reuse the restored access token if it is still valid
3. Refresh the access token if it is close to expiry but the refresh token is still valid
4. Log in by refresh token if the access token has already expired
5. Fall back to username/password plus `mafile` if no stored session can be reused

This package is designed for bots that stay online for a long time and should not re-login before every trade action.

## Requirements

- Python 3.11+
- A `steampy` build that supports refresh-token login
- `cryptography` if you want encrypted session storage

## Quick Start

```python
from pathlib import Path

from steam_auth import AccountManager, SteamLoginOptions, build_default_session_store

session_store = build_default_session_store(
    data_dir=Path("data/buff_bot"),
    allow_plaintext_fallback=True,
)

manager = AccountManager.from_sources(
    accounts_file=Path("accounts/accounts.txt"),
    mafiles_dir=Path("accounts/mafiles"),
    session_store=session_store,
    options=SteamLoginOptions(),
)

results = manager.batch_login(delay_range=(2.0, 5.0))
account_map = manager.get_steamid_account_map()
account = account_map["7656119xxxxxxxxxx"]
client = account.ensure_client()
response = client.accept_trade_offer("1234567890")
```

## accounts.txt Format

```text
steam_username_1----steam_password_1
steam_username_2----steam_password_2
```

## mafile Requirements

Each `mafile` must contain at least:

- `account_name`
- `shared_secret`
- `identity_secret`

Both `*.mafile` and `*.maFile` are supported.

## Session Storage

By default the package prefers encrypted storage:

- Encrypted: `sessions.enc` plus `.key`
- Fallback: `sessions.json` when encryption dependencies are unavailable and fallback is allowed

Stored session data includes:

- `refresh_token`
- `refresh_token_expires_at`
- `access_token`
- `access_token_expires_at`
- cookies needed to restore the Steam web session

## Public API

- `AccountManager`: load, manage, and batch-login multiple accounts
- `SteamAccountClient`: wrap a single `SteamClient` with lazy login behavior
- `SteamAuthService`: one-shot login facade
- `build_default_session_store()`: create the default encrypted/plaintext store
- `login_and_get_client()`: convenience helper for direct login

## Notes

- The package touches several `steampy` internals such as `_session`, `_access_token`, and `was_login_executed`
- If the `.key` file is lost, encrypted sessions can no longer be decrypted
- If both the access token and refresh token are expired, the package falls back to password login

## License

This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.
