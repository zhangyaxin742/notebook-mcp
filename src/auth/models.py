from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


@dataclass(frozen=True)
class NotebookLMSession:
    cookies: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    headers: dict[str, str] = field(default_factory=dict)
    csrf_token: str | None = None
    user_agent: str | None = None
    notebooklm_origin: str = "https://notebooklm.google.com"
    updated_at: str = field(default_factory=utc_now_iso)
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "NotebookLMSession":
        cookies = payload.get("cookies") or []
        headers = payload.get("headers") or {}
        metadata = payload.get("metadata") or {}
        return cls(
            cookies=tuple(dict(cookie) for cookie in cookies),
            headers={str(key): str(value) for key, value in headers.items()},
            csrf_token=payload.get("csrf_token"),
            user_agent=payload.get("user_agent"),
            notebooklm_origin=payload.get("notebooklm_origin", "https://notebooklm.google.com"),
            updated_at=payload.get("updated_at", utc_now_iso()),
            expires_at=payload.get("expires_at"),
            metadata=dict(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cookies": [dict(cookie) for cookie in self.cookies],
            "headers": dict(sorted(self.headers.items())),
            "csrf_token": self.csrf_token,
            "user_agent": self.user_agent,
            "notebooklm_origin": self.notebooklm_origin,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "metadata": dict(sorted(self.metadata.items())),
        }

    def cookie_count(self) -> int:
        return len(self.cookies)

    def has_auth_material(self) -> bool:
        return bool(self.cookies)

    def computed_expiry(self) -> datetime | None:
        explicit_expiry = _parse_iso8601(self.expires_at)
        if explicit_expiry is not None:
            return explicit_expiry
        expirations: list[datetime] = []
        for cookie in self.cookies:
            raw_expiry = cookie.get("expires")
            if isinstance(raw_expiry, (int, float)) and raw_expiry > 0:
                expirations.append(datetime.fromtimestamp(raw_expiry, tz=timezone.utc))
        return min(expirations) if expirations else None

    def is_expired(self, now: datetime | None = None) -> bool:
        expiry = self.computed_expiry()
        if expiry is None:
            return False
        current = now or datetime.now(timezone.utc)
        return expiry <= current

    def summary(self) -> dict[str, Any]:
        cookie_names = sorted(
            str(cookie.get("name"))
            for cookie in self.cookies
            if cookie.get("name")
        )
        return {
            "cookie_count": self.cookie_count(),
            "cookie_names": cookie_names,
            "has_headers": bool(self.headers),
            "has_csrf_token": bool(self.csrf_token),
            "user_agent_present": bool(self.user_agent),
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "notebooklm_origin": self.notebooklm_origin,
        }


@dataclass(frozen=True)
class AuthValidationResult:
    ok: bool
    code: str
    message: str
    session_summary: dict[str, Any] = field(default_factory=dict)

