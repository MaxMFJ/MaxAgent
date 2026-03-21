"""
macOS Keychain helper for secure API key storage.
Uses the `security` CLI tool (always available on macOS).
Falls back to plaintext if Keychain is unavailable.
"""

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

_SERVICE_NAME = "com.macagent.llm-config"
_IS_MACOS = sys.platform == "darwin"


def keychain_store(account: str, secret: str) -> bool:
    """Store a secret in macOS Keychain. Returns True on success."""
    if not _IS_MACOS or not secret:
        return False
    try:
        # Delete existing entry first (ignore errors)
        subprocess.run(
            ["security", "delete-generic-password", "-s", _SERVICE_NAME, "-a", account],
            capture_output=True, timeout=5,
        )
        result = subprocess.run(
            ["security", "add-generic-password",
             "-s", _SERVICE_NAME, "-a", account, "-w", secret,
             "-U"],  # -U = update if exists
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            logger.info(f"[keychain] Stored secret for account '{account}'")
            return True
        logger.warning(f"[keychain] Failed to store: {result.stderr.strip()}")
        return False
    except Exception as e:
        logger.warning(f"[keychain] Store error: {e}")
        return False


def keychain_load(account: str) -> str | None:
    """Load a secret from macOS Keychain. Returns None if unavailable."""
    if not _IS_MACOS:
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password",
             "-s", _SERVICE_NAME, "-a", account, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            secret = result.stdout.strip()
            if secret:
                return secret
        return None
    except Exception as e:
        logger.debug(f"[keychain] Load error for '{account}': {e}")
        return None


def keychain_delete(account: str) -> bool:
    """Delete a secret from macOS Keychain."""
    if not _IS_MACOS:
        return False
    try:
        result = subprocess.run(
            ["security", "delete-generic-password",
             "-s", _SERVICE_NAME, "-a", account],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False
