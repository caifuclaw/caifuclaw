# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from .settings import get_settings


class CredentialManager:
    """CaifuClaw AI 本地凭据加密管理器。"""

    def __init__(self, encryption_key: str | bytes | None = None):
        if encryption_key is None:
            settings = get_settings()
            encryption_key = settings.fernet_key or _derive_fernet_key(settings.sync_secret_key)
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode("utf-8")
        self.fernet = Fernet(encryption_key)

    def encrypt_credentials(self, credentials: dict) -> bytes:
        if not isinstance(credentials, dict):
            raise ValueError("Credentials must be a dictionary")
        return self.fernet.encrypt(json.dumps(credentials, ensure_ascii=False).encode("utf-8"))

    def decrypt_credentials(self, encrypted_data: bytes | str | None) -> dict:
        if not encrypted_data:
            return {}
        if isinstance(encrypted_data, str):
            encrypted_data = encrypted_data.encode("utf-8")
        try:
            return json.loads(self.fernet.decrypt(encrypted_data).decode("utf-8"))
        except InvalidToken as exc:
            raise InvalidToken(f"Failed to decrypt credentials: {exc}") from exc

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("utf-8")


def _derive_fernet_key(seed: str) -> bytes:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


_credential_manager: CredentialManager | None = None


def get_credential_manager() -> CredentialManager:
    global _credential_manager
    if _credential_manager is None:
        _credential_manager = CredentialManager()
    return _credential_manager


def init_credential_manager(encryption_key: str | bytes | None = None) -> CredentialManager:
    global _credential_manager
    _credential_manager = CredentialManager(encryption_key)
    return _credential_manager

