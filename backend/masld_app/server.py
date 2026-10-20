"""Start the loopback-only frontend and API server."""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from threading import BoundedSemaphore

from .api.handler import RequestHandler, SlidingWindowRateLimiter
from .config import WEB_ROOT, Settings, ensure_supported_runtime, load_settings
from .services.artifacts import initialize_runtime_model

logger = logging.getLogger(__name__)


class LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[RequestHandler],
        settings: Settings,
    ) -> None:
        self.max_request_bytes = settings.max_request_bytes
        self.socket_timeout_seconds = settings.socket_timeout_seconds
        self._worker_slots = BoundedSemaphore(settings.max_concurrent_requests)
        self.rate_limiter = SlidingWindowRateLimiter(settings.api_requests_per_minute)
        super().__init__(address, handler)

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        request, client_address = super().get_request()
        request.settimeout(self.socket_timeout_seconds)
        return request, client_address

    def process_request(
        self, request: socket.socket, client_address: tuple[str, int]
    ) -> None:
        if not self._worker_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\nContent-Length: 0\r\nRetry-After: 2\r\n\r\n"
                )
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            worker = threading.Thread(
                target=self.process_request_thread,
                args=(request, client_address),
                daemon=self.daemon_threads,
            )
            worker.start()
        except RuntimeError:
            self._worker_slots.release()
            self.handle_error(request, client_address)
            self.shutdown_request(request)

    def process_request_thread(
        self, request: socket.socket, client_address: tuple[str, int]
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, help="override the port from MASLD_PORT")
    args = parser.parse_args()
    try:
        ensure_supported_runtime()
        settings = load_settings()
        port = args.port if args.port is not None else settings.port
        if not 1024 <= port <= 65535:
            parser.error("port must be in the range 1024..65535")
        _, model_source = initialize_runtime_model()
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Startup configuration or model error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if model_source == "in-memory synthetic fallback":
        logger.warning(
            "Packaged model artifact is missing or invalid; "
            "running a memory-only synthetic fallback. "
            "Retrain to restore the checked-in artifact."
        )
    handler = partial(RequestHandler, directory=str(WEB_ROOT))
    try:
        server = LocalHTTPServer((settings.host, port), handler, settings)
    except OSError as exc:
        print(f"Could not start local server: {exc}", file=sys.stderr)
        return 2
    print(f"Local model frontend: http://127.0.0.1:{port}/")
    print("Serving only on loopback. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local server.")
    finally:
        server.server_close()
    return 0
