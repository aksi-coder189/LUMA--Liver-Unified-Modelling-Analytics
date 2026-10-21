"""HTTP adapter for static frontend assets and the versioned JSON API."""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import OrderedDict, deque
from http.server import SimpleHTTPRequestHandler
from typing import Any
from urllib.parse import urlsplit

from .errors import APIError
from .routes import GET_ROUTES, POST_ROUTES

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Bound API requests per client without retaining unbounded client keys."""

    def __init__(self, requests_per_minute: int, max_clients: int = 2048) -> None:
        self.requests_per_minute = requests_per_minute
        self.max_clients = max_clients
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, client: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            events = self._events.get(client)
            if events is None:
                if len(self._events) >= self.max_clients:
                    self._events.popitem(last=False)
                events = deque()
                self._events[client] = events
            else:
                self._events.move_to_end(client)
            while events and now - events[0] >= 60:
                events.popleft()
            if len(events) >= self.requests_per_minute:
                retry_after = max(1, math.ceil(60 - (now - events[0])))
                return False, retry_after
            events.append(now)
            return True, 0


class RequestHandler(SimpleHTTPRequestHandler):
    server_version = "MASLDLocal/1.0"

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        )
        if urlsplit(self.path).path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, _format: str, *_args: Any) -> None:
        # The stdlib default logs the entire request target, including query strings.
        path = urlsplit(self.path).path[:256]
        logger.info("%s %s %r", self.client_address[0], self.command, path)

    
    def _is_allowed_authority(self, value: str | None) -> bool:
        import os

        if not value:
            return False
        try:
            authority = urlsplit("//" + value)
            render_host = os.environ.get(
                "RENDER_EXTERNAL_HOSTNAME", ""
            ).strip().lower()

            hostname = (authority.hostname or "").lower()
            allowed_hosts = {"127.0.0.1", "localhost"}
            if render_host:
                allowed_hosts.add(render_host)

            return (
                authority.username is None
                and authority.password is None
                and authority.path in ("", "/")
                and authority.query == ""
                and authority.fragment == ""
                and hostname in allowed_hosts
                and (
                    authority.port == self.server.server_port
                    or (
                        hostname == render_host
                        and authority.port is None
                    )
                )
            )
        except ValueError:
            return False

    
    def _is_local_origin(self, value: str) -> bool:
        import os

        try:
            origin = urlsplit(value)
            render_host = os.environ.get(
                "RENDER_EXTERNAL_HOSTNAME", ""
            ).strip().lower()

            if (
                origin.username is not None
                or origin.password is not None
                or origin.path not in ("", "/")
                or origin.query
                or origin.fragment
            ):
                return False

            hostname = (origin.hostname or "").lower()

            if render_host and hostname == render_host:
                return origin.scheme == "https" and origin.port in (None, 443)

            return (
                origin.scheme == "http"
                and hostname in {"127.0.0.1", "localhost"}
                and origin.port == self.server.server_port
            )
        except ValueError:
            return False


    def _request_is_local(self, *, check_origin: bool) -> bool:
        if not self._is_allowed_authority(self.headers.get("Host")):
            self._error(
                403,
                "INVALID_HOST",
                "This local service only accepts its loopback host.",
            )
            return False
        origin = self.headers.get("Origin")
        fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        if check_origin and (
            (origin is not None and not self._is_local_origin(origin))
            or fetch_site == "cross-site"
        ):
            self._error(
                403,
                "CROSS_ORIGIN_BLOCKED",
                "Cross-origin requests are not accepted by this local service.",
            )
            return False
        return True

    def _within_rate_limit(self) -> bool:
        allowed, retry_after = self.server.rate_limiter.allow(self.client_address[0])
        if not allowed:
            self._error(
                429,
                "RATE_LIMITED",
                "Too many local API requests. Wait before trying again.",
                headers={"Retry-After": str(retry_after)},
            )
            return False
        return True

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if not self._request_is_local(check_origin=False):
            return
        if path.startswith("/api/") and not self._within_rate_limit():
            return
        route = GET_ROUTES.get(path)
        if route is not None:
            self._dispatch(route, b"")
            return
        if path.startswith("/api/"):
            self._error(404, "NOT_FOUND", "API route not found.")
            return
        self.path = "/index.html" if path == "/" else self.path
        super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if not self._request_is_local(check_origin=True):
            return
        if not self._within_rate_limit():
            return
        route = POST_ROUTES.get(path)
        if route is None:
            self._error(404, "NOT_FOUND", "API route not found.")
            return
        content_type = (
            self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        )
        if content_type != "application/json":
            self._error(
                415, "UNSUPPORTED_MEDIA_TYPE", "Send Content-Type: application/json."
            )
            return
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            self._error(
                400,
                "INVALID_CONTENT_LENGTH",
                "Content-Length must be a non-negative integer.",
            )
            return
        if length < 0:
            self._error(411, "LENGTH_REQUIRED", "Content-Length is required.")
            return
        if length > self.server.max_request_bytes:
            self._error(
                413,
                "REQUEST_TOO_LARGE",
                "Request body exceeds the configured size limit.",
            )
            return
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                self._error(
                    400,
                    "INCOMPLETE_BODY",
                    "Request body ended before Content-Length bytes were received.",
                )
                return
            self._dispatch(route, body)
        except (ConnectionError, TimeoutError):
            logger.info("Client disconnected while sending request body")

    def _dispatch(self, route: Any, body: bytes) -> None:
        try:
            status, payload = route(body)
            # Use your existing response method here.
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(payload, allow_nan=False).encode("utf-8"))
        except APIError as exc:
            self._error(exc.status, exc.code, exc.message)
        except (TypeError, ValueError) as exc:
            self._error(400, "INVALID_INPUT", str(exc))
        except Exception:
            logger.exception(
                "Unhandled API error for %s",
                urlsplit(self.path).path,
            )
            self._error(
                500,
                "INTERNAL_ERROR",
                "The local server could not complete this request.",
            )

    def _error(
        self,
        status: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._json(
            status, {"error": {"code": code, "message": message}}, headers=headers
        )

    def _json(
        self,
        status: int,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        try:
            encoded = json.dumps(body, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            logger.info("Client disconnected before response completed")
