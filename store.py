from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock

from .exceptions import DependencyUnavailableError, SessionStoreError
from .models import SessionData


def _serialize_sessions(cache: dict[str, SessionData]) -> str:
    """序列化会话缓存。 / Serialize the in-memory session cache to JSON text."""
    payload = {key: value.to_dict() for key, value in cache.items()}
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _deserialize_sessions(text: str) -> dict[str, SessionData]:
    """反序列化会话缓存。 / Deserialize JSON text into session cache objects."""
    if not text.strip():
        return {}
    raw = json.loads(text)
    return {str(key): SessionData.from_dict(value) for key, value in raw.items()}


class SessionStore(ABC):
    @abstractmethod
    def load(self) -> dict[str, SessionData]:
        """加载全部会话。 / Load all stored sessions into memory."""
        raise NotImplementedError

    @abstractmethod
    def save(self) -> None:
        """保存当前缓存。 / Persist the current in-memory cache."""
        raise NotImplementedError

    @abstractmethod
    def get(self, username: str) -> SessionData | None:
        """读取单个会话。 / Fetch a stored session by username."""
        raise NotImplementedError

    @abstractmethod
    def set(self, session: SessionData) -> None:
        """写入单个会话。 / Store or replace one session entry."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, username: str) -> None:
        """删除单个会话。 / Delete one stored session by username."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """清空全部会话。 / Remove all stored sessions."""
        raise NotImplementedError


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        """初始化内存存储。 / Initialize a purely in-memory session store."""
        self._cache: dict[str, SessionData] = {}

    def load(self) -> dict[str, SessionData]:
        """返回缓存副本。 / Return a copy of the in-memory cache."""
        return dict(self._cache)

    def save(self) -> None:
        """内存存储无需持久化。 / No-op because in-memory storage has nothing to persist."""
        return None

    def get(self, username: str) -> SessionData | None:
        """读取缓存中的会话。 / Get a session from the in-memory cache."""
        return self._cache.get(username)

    def set(self, session: SessionData) -> None:
        """更新缓存中的会话。 / Upsert a session in the in-memory cache."""
        self._cache[session.username] = session

    def delete(self, username: str) -> None:
        """删除缓存中的会话。 / Delete a session from the in-memory cache."""
        self._cache.pop(username, None)

    def clear(self) -> None:
        """清空缓存。 / Clear the in-memory cache."""
        self._cache.clear()


class JsonFileStore(SessionStore):
    def __init__(self, file_path: str | Path) -> None:
        """初始化 JSON 文件存储。 / Initialize a plaintext JSON-backed session store."""
        self.file_path = Path(file_path)
        self._cache: dict[str, SessionData] = {}
        self._loaded = False
        self._lock = RLock()

    def load(self) -> dict[str, SessionData]:
        """从 JSON 文件加载会话。 / Load sessions from the JSON file."""
        with self._lock:
            if not self.file_path.exists():
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                self._cache = {}
                self._loaded = True
                return {}

            try:
                text = self.file_path.read_text(encoding="utf-8")
                self._cache = _deserialize_sessions(text)
                self._loaded = True
                return dict(self._cache)
            except OSError as exc:
                raise SessionStoreError(f"cannot read session store: {self.file_path}") from exc
            except json.JSONDecodeError as exc:
                raise SessionStoreError(f"invalid session store JSON: {self.file_path}") from exc

    def save(self) -> None:
        """将缓存写回 JSON 文件。 / Save the current cache to the JSON file."""
        with self._lock:
            if not self._loaded:
                self.load()
            try:
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                self.file_path.write_text(_serialize_sessions(self._cache), encoding="utf-8")
            except OSError as exc:
                raise SessionStoreError(f"cannot write session store: {self.file_path}") from exc

    def get(self, username: str) -> SessionData | None:
        """读取指定用户会话。 / Get one session from the JSON store."""
        if not self._loaded:
            self.load()
        return self._cache.get(username)

    def set(self, session: SessionData) -> None:
        """写入指定用户会话。 / Store one session in the JSON file store."""
        if not self._loaded:
            self.load()
        self._cache[session.username] = session
        self.save()

    def delete(self, username: str) -> None:
        """删除指定用户会话。 / Delete one session from the JSON file store."""
        if not self._loaded:
            self.load()
        if username in self._cache:
            del self._cache[username]
            self.save()

    def clear(self) -> None:
        """清空 JSON 存储。 / Clear all sessions from the JSON file store."""
        if not self._loaded:
            self.load()
        self._cache.clear()
        self.save()


class EncryptedFileStore(SessionStore):
    def __init__(
        self,
        data_dir: str | Path,
        sessions_file: str | Path | None = None,
        key_file: str | Path | None = None,
    ) -> None:
        """初始化加密文件存储。 / Initialize an encrypted file-backed session store."""
        self.data_dir = Path(data_dir)
        self.sessions_file = Path(sessions_file) if sessions_file else self.data_dir / "sessions.enc"
        self.key_file = Path(key_file) if key_file else self.data_dir / ".key"
        self._cache: dict[str, SessionData] = {}
        self._loaded = False
        self._lock = RLock()

    def _get_fernet(self):
        """获取或创建 Fernet 实例。 / Get or create the Fernet helper used for encryption."""
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise DependencyUnavailableError(
                "EncryptedFileStore requires the 'cryptography' package"
            ) from exc

        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.key_file.exists():
            self.key_file.write_bytes(Fernet.generate_key())
        return Fernet(self.key_file.read_bytes())

    def load(self) -> dict[str, SessionData]:
        """从加密文件加载会话。 / Load sessions from the encrypted file store."""
        with self._lock:
            if not self.sessions_file.exists():
                self.data_dir.mkdir(parents=True, exist_ok=True)
                self._cache = {}
                self._loaded = True
                return {}

            try:
                fernet = self._get_fernet()
                plaintext = fernet.decrypt(self.sessions_file.read_bytes()).decode("utf-8")
                self._cache = _deserialize_sessions(plaintext)
                self._loaded = True
                return dict(self._cache)
            except DependencyUnavailableError:
                raise
            except Exception as exc:
                raise SessionStoreError(f"cannot load encrypted sessions: {self.sessions_file}") from exc

    def save(self) -> None:
        """将缓存加密后写入磁盘。 / Encrypt and save the current cache to disk."""
        with self._lock:
            if not self._loaded:
                self.load()
            try:
                fernet = self._get_fernet()
                ciphertext = fernet.encrypt(_serialize_sessions(self._cache).encode("utf-8"))
                self.data_dir.mkdir(parents=True, exist_ok=True)
                self.sessions_file.write_bytes(ciphertext)
            except DependencyUnavailableError:
                raise
            except Exception as exc:
                raise SessionStoreError(f"cannot save encrypted sessions: {self.sessions_file}") from exc

    def get(self, username: str) -> SessionData | None:
        """读取指定用户会话。 / Get one session from the encrypted store."""
        if not self._loaded:
            self.load()
        return self._cache.get(username)

    def set(self, session: SessionData) -> None:
        """写入指定用户会话。 / Store one session in the encrypted file store."""
        if not self._loaded:
            self.load()
        self._cache[session.username] = session
        self.save()

    def delete(self, username: str) -> None:
        """删除指定用户会话。 / Delete one session from the encrypted store."""
        if not self._loaded:
            self.load()
        if username in self._cache:
            del self._cache[username]
            self.save()

    def clear(self) -> None:
        """清空全部加密会话。 / Clear all sessions from the encrypted store."""
        if not self._loaded:
            self.load()
        self._cache.clear()
        self.save()
