from __future__ import annotations

import base64
import ctypes
from ctypes import POINTER, Structure, byref, cast
from ctypes import wintypes
import json
import os
from pathlib import Path
from typing import Any

from .config import AuthRuntimePaths
from .models import NotebookLMSession


SESSION_STORE_VERSION = 2


class _DataBlob(Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", POINTER(ctypes.c_char)),
    ]


class SessionProtectionError(RuntimeError):
    pass


class SessionStore:
    def __init__(self, paths: AuthRuntimePaths) -> None:
        self._paths = paths

    @property
    def session_file(self) -> Path:
        return self._paths.session_file

    def load(self) -> NotebookLMSession | None:
        if not self.session_file.exists():
            return None

        with self.session_file.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)

        if self._is_legacy_plaintext_payload(payload):
            session = NotebookLMSession.from_dict(payload)
            self.save(session)
            return session

        if not isinstance(payload, dict):
            raise SessionProtectionError("Session file does not contain a supported JSON object.")

        storage_kind = payload.get("storage_kind")
        if storage_kind == "windows_dpapi":
            ciphertext_b64 = payload.get("ciphertext_b64")
            if not isinstance(ciphertext_b64, str) or not ciphertext_b64:
                raise SessionProtectionError("Encrypted session file is missing ciphertext.")
            plaintext = _decrypt_windows_dpapi(base64.b64decode(ciphertext_b64))
            return NotebookLMSession.from_dict(json.loads(plaintext.decode("utf-8")))

        if storage_kind == "restricted_plaintext":
            session_payload = payload.get("payload")
            if not isinstance(session_payload, dict):
                raise SessionProtectionError("Restricted plaintext session is missing payload data.")
            return NotebookLMSession.from_dict(session_payload)

        raise SessionProtectionError(f"Unsupported session storage kind: {storage_kind!r}")

    def save(self, session: NotebookLMSession) -> Path:
        self._paths.ensure_directories()
        envelope = self._build_envelope(session)
        with self.session_file.open("w", encoding="utf-8") as handle:
            json.dump(envelope, handle, indent=2, sort_keys=True)
            handle.write("\n")
        self._apply_file_permissions(self.session_file)
        return self.session_file

    def delete(self) -> None:
        if self.session_file.exists():
            self.session_file.unlink()

    def describe_storage(self) -> dict[str, Any]:
        if not self.session_file.exists():
            return {
                "exists": False,
                "storage_kind": "missing",
                "encrypted": False,
                "warning": None,
            }

        try:
            with self.session_file.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        except Exception as exc:
            return {
                "exists": True,
                "storage_kind": "unreadable",
                "encrypted": False,
                "warning": f"Session file could not be inspected: {exc}",
            }

        if self._is_legacy_plaintext_payload(payload):
            return {
                "exists": True,
                "storage_kind": "legacy_plaintext",
                "encrypted": False,
                "warning": "Session file is legacy plaintext and should be rewritten through the auth manager.",
            }

        if not isinstance(payload, dict):
            return {
                "exists": True,
                "storage_kind": "unrecognized",
                "encrypted": False,
                "warning": "Session file format is not recognized.",
            }

        storage_kind = str(payload.get("storage_kind", "unrecognized"))
        warning = payload.get("warning")
        encrypted = storage_kind == "windows_dpapi"
        if storage_kind == "restricted_plaintext" and not warning:
            warning = (
                "Session storage is permission-hardened plaintext because strong OS-backed encryption "
                "is not available on this runtime."
            )
        return {
            "exists": True,
            "storage_kind": storage_kind,
            "encrypted": encrypted,
            "warning": warning,
        }

    def _build_envelope(self, session: NotebookLMSession) -> dict[str, Any]:
        plaintext = json.dumps(session.to_dict(), sort_keys=True).encode("utf-8")
        if _windows_dpapi_available():
            ciphertext = _encrypt_windows_dpapi(plaintext)
            return {
                "version": SESSION_STORE_VERSION,
                "storage_kind": "windows_dpapi",
                "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            }

        return {
            "version": SESSION_STORE_VERSION,
            "storage_kind": "restricted_plaintext",
            "warning": (
                "Strong OS-backed encryption is unavailable on this runtime. "
                "This file is permission-hardened but still contains plaintext auth material."
            ),
            "payload": session.to_dict(),
        }

    @staticmethod
    def _is_legacy_plaintext_payload(payload: Any) -> bool:
        return isinstance(payload, dict) and "cookies" in payload and "storage_kind" not in payload

    @staticmethod
    def _apply_file_permissions(path: Path) -> None:
        try:
            os.chmod(path, 0o600)
        except OSError:
            return


def _windows_dpapi_available() -> bool:
    return os.name == "nt" and hasattr(ctypes, "windll")


def _blob_from_bytes(raw_bytes: bytes) -> _DataBlob:
    buffer = ctypes.create_string_buffer(raw_bytes, len(raw_bytes))
    blob = _DataBlob()
    blob.cbData = len(raw_bytes)
    blob.pbData = cast(buffer, POINTER(ctypes.c_char))
    blob._buffer = buffer  # type: ignore[attr-defined]
    return blob


def _bytes_from_blob(blob: _DataBlob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _encrypt_windows_dpapi(plaintext: bytes) -> bytes:
    if not _windows_dpapi_available():
        raise SessionProtectionError("Windows DPAPI is unavailable on this runtime.")

    input_blob = _blob_from_bytes(plaintext)
    output_blob = _DataBlob()
    crypt_protect = ctypes.windll.crypt32.CryptProtectData
    local_free = ctypes.windll.kernel32.LocalFree

    success = crypt_protect(
        byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        byref(output_blob),
    )
    if not success:
        raise ctypes.WinError()

    try:
        return _bytes_from_blob(output_blob)
    finally:
        local_free(output_blob.pbData)


def _decrypt_windows_dpapi(ciphertext: bytes) -> bytes:
    if not _windows_dpapi_available():
        raise SessionProtectionError("Windows DPAPI is unavailable on this runtime.")

    input_blob = _blob_from_bytes(ciphertext)
    output_blob = _DataBlob()
    crypt_unprotect = ctypes.windll.crypt32.CryptUnprotectData
    local_free = ctypes.windll.kernel32.LocalFree

    success = crypt_unprotect(
        byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        byref(output_blob),
    )
    if not success:
        raise ctypes.WinError()

    try:
        return _bytes_from_blob(output_blob)
    finally:
        local_free(output_blob.pbData)
