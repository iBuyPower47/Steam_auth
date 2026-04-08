# steam_auth

[English](./README.md)

`steam_auth` 是一个面向长期挂机自动化场景的 Steam 登录编排模块。
它优先从本地恢复会话，只在确实需要时刷新 token，只有本地会话完全不可用时才回退到账号密码登录。

## 功能特性

- 统一封装 Cookie 恢复、Refresh Token 登录、密码登录
- 基于本地 `access_token` 过期时间判断，避免频繁远程探测登录状态
- 支持加密会话存储，并可在允许时回退为明文 JSON 存储
- 支持从 `accounts.txt` 和 Steam Desktop Authenticator `mafile` 批量加载账号
- 支持按 `steamid` 路由到具体账号客户端

## 目录结构

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

## 登录策略

登录流程按以下顺序执行：

1. 从本地会话存储恢复 cookies 和 token
2. 如果恢复出的 `access_token` 仍有效，直接复用
3. 如果 `access_token` 临近过期且 `refresh_token` 仍有效，优先刷新 access token
4. 如果 `access_token` 已过期，但 `refresh_token` 仍有效，则走 refresh-token 登录
5. 如果本地会话无法继续使用，则回退到账号密码加 `mafile` 登录

这个模块适合长期运行的机器人程序，不需要在每次交易前重新登录。

## 运行要求

- Python 3.11+
- 支持 refresh-token 登录的 `steampy`
- 如需加密存储，需安装 `cryptography`

## 快速开始

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

## accounts.txt 格式

```text
steam_username_1----steam_password_1
steam_username_2----steam_password_2
```

## mafile 要求

每个 `mafile` 至少需要包含：

- `account_name`
- `shared_secret`
- `identity_secret`

同时兼容 `*.mafile` 和 `*.maFile`。

## 会话存储

默认优先使用加密存储：

- 加密存储：`sessions.enc` + `.key`
- 降级存储：当加密依赖不可用且允许降级时，使用 `sessions.json`

会话数据中会保存：

- `refresh_token`
- `refresh_token_expires_at`
- `access_token`
- `access_token_expires_at`
- 恢复 Steam Web 会话所需的 cookies

## 对外接口

- `AccountManager`：加载、管理并批量登录多个账号
- `SteamAccountClient`：单账号客户端包装器，提供按需登录能力
- `SteamAuthService`：一次性登录门面
- `build_default_session_store()`：构建默认会话存储
- `login_and_get_client()`：直接登录的便捷方法

## 注意事项

- 模块内部依赖了 `steampy` 的部分私有属性，如 `_session`、`_access_token`、`was_login_executed`
- 如果 `.key` 文件丢失，加密会话将无法解密，只能重新登录
- 当 `access_token` 和 `refresh_token` 都失效时，会自动回退到密码登录

## License

如将该模块独立发布，建议沿用上层仓库的许可证，或在拆分时单独补充许可证说明。
