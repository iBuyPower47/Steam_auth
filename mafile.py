from __future__ import annotations

import json
from pathlib import Path

from .exceptions import MaFileError

REQUIRED_MAFILE_KEYS = ("account_name", "shared_secret", "identity_secret")


def load_mafile(path: str | Path) -> dict:
    """加载并校验单个 mafile。 / Load and validate a single Steam Desktop Authenticator mafile."""
    mafile_path = Path(path)
    if not mafile_path.exists():
        raise MaFileError(f"读取不到 mafile 令牌文件: {mafile_path}")

    try:
        with mafile_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise MaFileError(f"无效的令牌文件 JSON 格式: {mafile_path}") from exc
    except OSError as exc:
        raise MaFileError(f"无法读取 mafile 文件: {mafile_path}") from exc

    return validate_mafile(payload, source=mafile_path)


def validate_mafile(payload: dict, source: str | Path | None = None) -> dict:
    """校验并标准化 mafile 数据。 / Validate and normalize mafile payload data."""
    missing = [key for key in REQUIRED_MAFILE_KEYS if not payload.get(key)]
    if missing:
        origin = f"，来源: {source}" if source else ""
        missing_keys = ", ".join(missing)
        raise MaFileError(f"令牌缺少必要字段{origin}: {missing_keys}")

    normalized = dict(payload)
    if normalized.get("steamid") is not None:
        normalized["steamid"] = str(normalized["steamid"])
    normalized["account_name"] = str(normalized["account_name"])
    normalized["shared_secret"] = str(normalized["shared_secret"])
    normalized["identity_secret"] = str(normalized["identity_secret"])
    return normalized


def scan_mafiles(mafiles_dir: str | Path) -> dict[str, Path]:
    """扫描目录中的全部 mafile。 / Scan a directory and map account names to mafile paths."""
    directory = Path(mafiles_dir)
    if not directory.exists():
        raise MaFileError(f"mafile 目录不存在: {directory}")

    result: dict[str, Path] = {}
    for pattern in ("*.mafile", "*.maFile"):
        for path in sorted(directory.glob(pattern)):
            data = load_mafile(path)
            result[data["account_name"]] = path
    return result
