class SteamAuthError(Exception):
    """Steam 认证模块基础异常。 / Base exception for the Steam auth package."""


class SteamLoginError(SteamAuthError):
    """Steam 登录流程失败。 / Raised when the Steam login flow fails."""


class CredentialsError(SteamLoginError):
    """登录凭证或输入参数无效。 / Raised when credentials or login inputs are invalid."""


class MaFileError(SteamAuthError):
    """mafile 令牌文件无效。 / Raised when an SDA mafile is invalid."""


class SessionStoreError(SteamAuthError):
    """会话持久化失败。 / Raised when session persistence fails."""


class DependencyUnavailableError(SteamAuthError):
    """缺少可选运行时依赖。 / Raised when an optional runtime dependency is missing."""
