"""Runtime settings read from environment variables, with local safe defaults."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"


def ensure_supported_runtime() -> None:
    """Refuse known-outdated Python patch lines used for serving the prototype."""
    version = sys.version_info
    supported = version.releaselevel == "final" and (
        version.major > 3
        or (
            version.major == 3
            and (
                (version.minor == 13 and version.micro >= 16)
                or (version.minor == 14 and version.micro >= 8)
                or version.minor > 14
            )
        )
    )
    if not supported:
        raise RuntimeError(
            "This prototype requires a patched Python runtime: use Python 3.13.16+ "
            "or Python 3.14.8+ (or a later stable release)."
        )


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    max_request_bytes: int = 64 * 1024
    api_requests_per_minute: int = 60
    max_concurrent_requests: int = 16
    socket_timeout_seconds: int = 10


def load_settings() -> Settings:
    host = os.environ.get("MASLD_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError(
            "MASLD_HOST must be 127.0.0.1 or localhost; this prototype is local-only."
        )
    try:
        port = int(os.environ.get("MASLD_PORT", "8765"))
        max_body = int(os.environ.get("MASLD_MAX_REQUEST_BYTES", str(64 * 1024)))
        rate_limit = int(os.environ.get("MASLD_API_RATE_LIMIT_PER_MINUTE", "60"))
        max_workers = int(os.environ.get("MASLD_MAX_CONCURRENT_REQUESTS", "16"))
        socket_timeout = int(os.environ.get("MASLD_SOCKET_TIMEOUT_SECONDS", "10"))
    except ValueError as exc:
        raise ValueError(
            "MASLD_PORT and MASLD_MAX_REQUEST_BYTES must be integers."
        ) from exc
    if not 1024 <= port <= 65535:
        raise ValueError("MASLD_PORT must be between 1024 and 65535.")
    if not 1024 <= max_body <= 1024 * 1024:
        raise ValueError("MASLD_MAX_REQUEST_BYTES must be between 1024 and 1048576.")
    if not 1 <= rate_limit <= 600:
        raise ValueError("MASLD_API_RATE_LIMIT_PER_MINUTE must be between 1 and 600.")
    if not 1 <= max_workers <= 64:
        raise ValueError("MASLD_MAX_CONCURRENT_REQUESTS must be between 1 and 64.")
    if not 1 <= socket_timeout <= 60:
        raise ValueError("MASLD_SOCKET_TIMEOUT_SECONDS must be between 1 and 60.")
    return Settings(
        host=host,
        port=port,
        max_request_bytes=max_body,
        api_requests_per_minute=rate_limit,
        max_concurrent_requests=max_workers,
        socket_timeout_seconds=socket_timeout,
    )
