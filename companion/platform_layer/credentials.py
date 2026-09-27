"""Secure platform-native credential storage for DeskBot (macOS Keychain & Windows Credential Manager)."""

from __future__ import annotations

import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from .paths import get_app_data_dir

logger = logging.getLogger(__name__)

SERVICE_NAME = "DeskBot"
KEY_USERNAME = "nvidia_api_key"


class CredentialStore:
    """Manages secure storage and retrieval of credentials using native OS credential vaults."""

    def __init__(self, service_name: str = SERVICE_NAME, username: str = KEY_USERNAME):
        self.service_name = service_name
        self.username = username
        self._fallback_path = get_app_data_dir() / ".credential_vault"

    def get_api_key(self) -> Optional[str]:
        """Retrieve the API key from OS Keychain/Vault, falling back to environment variable.

        Never raises; returns None if no credential is saved.
        """
        # 1. Native OS Credential Store (Windows Credential Manager / macOS Keychain)
        try:
            import keyring
            key = keyring.get_password(self.service_name, self.username)
            if key and key.strip():
                return key.strip()
        except Exception as err:
            logger.debug("Keyring access error: %s", err)

        # 2. Local Environment Variable (Development Mode)
        env_key = os.getenv("NVIDIA_API_KEY")
        if env_key and env_key.strip():
            return env_key.strip()

        # 3. Protected local file fallback (Headless / non-GUI environments where keyring backend is absent)
        try:
            if self._fallback_path.exists():
                content = self._fallback_path.read_text(encoding="utf-8").strip()
                if content:
                    return content
        except Exception as err:
            logger.debug("Fallback credential file read error: %s", err)

        return None

    def set_api_key(self, api_key: str) -> bool:
        """Securely store the API key in the native OS vault.

        Returns True on success, False on error.
        """
        clean_key = (api_key or "").strip()
        if not clean_key:
            return False

        # Keep runtime environment in sync
        os.environ["NVIDIA_API_KEY"] = clean_key

        # 1. Store in native OS Credential Store
        keyring_saved = False
        try:
            import keyring
            keyring.set_password(self.service_name, self.username, clean_key)
            keyring_saved = True
        except Exception as err:
            logger.warning("Could not save to native OS keyring: %s", err)

        # 2. If keyring failed or unavailable, save to protected file
        if not keyring_saved:
            try:
                self._fallback_path.write_text(clean_key, encoding="utf-8")
                # Restrict file permissions to user-read/write only (POSIX 0600)
                if sys.platform != "win32":
                    os.chmod(self._fallback_path, 0o600)
                return True
            except Exception as err:
                logger.error("Could not write fallback credential file: %s", err)
                return False

        return True

    def delete_api_key(self) -> bool:
        """Remove the saved API key from the OS vault."""
        success = True
        try:
            import keyring
            keyring.delete_password(self.service_name, self.username)
        except Exception:
            pass

        if "NVIDIA_API_KEY" in os.environ:
            del os.environ["NVIDIA_API_KEY"]

        try:
            if self._fallback_path.exists():
                self._fallback_path.unlink()
        except Exception:
            success = False

        return success

    def has_api_key(self) -> bool:
        """Return True if an API key is available in OS storage or environment."""
        key = self.get_api_key()
        return bool(key and len(key) > 5)

    def get_masked_key(self) -> str:
        """Return a masked representation of the current key, e.g. 'nvapi-te...cdef' or 'Not Set'."""
        key = self.get_api_key()
        if not key:
            return "Not Set"
        if len(key) <= 12:
            return "********"
        return f"{key[:8]}...{key[-4:]}"

    def validate_api_key(self, api_key: str, timeout: float = 6.0) -> Tuple[bool, str]:
        """Test API key validity by querying NVIDIA NIM models endpoint.

        Returns (is_valid, message).
        """
        clean_key = (api_key or "").strip()
        if not clean_key:
            return False, "API key cannot be empty."

        url = "https://integrate.api.nvidia.com/v1/models"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {clean_key}",
                "User-Agent": "DeskBot-Verification/1.0",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True, "API key verified successfully with NVIDIA NIM."
                return False, f"Unexpected response code: {resp.status}"
        except urllib.error.HTTPError as http_err:
            if http_err.code in (401, 403):
                return False, "Invalid API key. Authentication failed with NVIDIA NIM."
            return False, f"NVIDIA API responded with error: {http_err.code} {http_err.reason}"
        except urllib.error.URLError as url_err:
            return False, f"Could not reach NVIDIA servers: {url_err.reason}"
        except Exception as err:
            return False, f"Verification error: {err}"


_GLOBAL_CREDENTIAL_STORE: Optional[CredentialStore] = None


def get_credential_store() -> CredentialStore:
    """Singleton getter for the credential store."""
    global _GLOBAL_CREDENTIAL_STORE
    if _GLOBAL_CREDENTIAL_STORE is None:
        _GLOBAL_CREDENTIAL_STORE = CredentialStore()
    return _GLOBAL_CREDENTIAL_STORE
