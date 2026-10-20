import json
import threading
from functools import partial
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from masld_app.api.handler import RequestHandler, SlidingWindowRateLimiter
from masld_app.config import WEB_ROOT, Settings
from masld_app.server import LocalHTTPServer


def test_rate_limiter_window():
    limiter = SlidingWindowRateLimiter(1)
    assert limiter.allow("127.0.0.1")[0]
    assert limiter.allow("127.0.0.1")[0] is False


def test_api_rejects_cross_origin_and_invalid_json_and_rate_limits():
    settings = Settings(
        api_requests_per_minute=30, max_concurrent_requests=4, max_request_bytes=1024
    )
    handler = partial(RequestHandler, directory=str(WEB_ROOT))
    server = LocalHTTPServer(("127.0.0.1", 0), handler, settings)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        request = Request(
            url + "/api/v1/model",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://evil.example",
            },
            method="POST",
        )
        try:
            urlopen(request, timeout=2)
            assert False, "cross-origin POST unexpectedly succeeded"
        except HTTPError as error:
            assert error.code == 403

        request = Request(
            url + "/api/v1/model",
            data=b"{",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(request, timeout=2)
            assert False, "malformed JSON unexpectedly succeeded"
        except HTTPError as error:
            assert error.code == 400
            assert json.loads(error.read())["error"]["code"] == "INVALID_JSON"

        unknown = Request(
            url + "/api/v1/model",
            data=b'{"unsupported_flag":true}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(unknown, timeout=2)
            assert False, "unknown field unexpectedly succeeded"
        except HTTPError as error:
            assert error.code == 400
            assert json.loads(error.read())["error"]["code"] == "INVALID_INPUT"

        for payload in (
            b"[]",
            b"null",
            b'{"age_years":NaN}',
            b'{"age_years":Infinity}',
            b'{"age_years":999}',
            b'{"reduce_uptake":"yes"}',
        ):
            request = Request(
                url + "/api/v1/model",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urlopen(request, timeout=2)
                assert False, f"invalid JSON input unexpectedly succeeded: {payload!r}"
            except HTTPError as error:
                assert error.code == 400
                assert json.loads(error.read())["error"]["code"] == "INVALID_INPUT"

        wrong_type = Request(
            url + "/api/v1/model",
            data=b"{}",
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        try:
            urlopen(wrong_type, timeout=2)
            assert False, "wrong content type unexpectedly succeeded"
        except HTTPError as error:
            assert error.code == 415

        too_large = Request(
            url + "/api/v1/model",
            data=b" " * 1025,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(too_large, timeout=2)
            assert False, "oversized body unexpectedly succeeded"
        except HTTPError as error:
            assert error.code == 413

        bad_host = Request(url + "/api/v1/health", headers={"Host": "evil.example"})
        try:
            urlopen(bad_host, timeout=2)
            assert False, "invalid Host unexpectedly succeeded"
        except HTTPError as error:
            assert error.code == 403

        valid = Request(
            url + "/api/v1/model",
            data=b'{"reduce_uptake":true}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(valid, timeout=5) as response:
            payload = json.loads(response.read())
            assert response.status == 200
            explanation = payload["mechanistic_simulation"]["explainability"]
            baseline_explanation = payload["scenario_vs_unmodified_toy_baseline"][
                "baseline_explainability"
            ]
            assert explanation["method"].startswith("For the fitted linear derivative")
            assert len(explanation["mean_trajectory"]["triglyceride"]) == 61
            assert len(baseline_explanation["zones"]) == 5
            assert (
                payload["mechanistic_simulation"]["assumptions_changed"][0]["parameter"]
                == "uptake"
            )

        with urlopen(url + "/api/v1/health", timeout=2) as response:
            health = json.loads(response.read())
            assert health["ok"] is True
            assert health["model_source"] == "checked-in artifact"
        with urlopen(url + "/api/health", timeout=2) as response:
            assert json.loads(response.read())["ok"] is True

        limited = False
        for _ in range(40):
            try:
                urlopen(url + "/api/v1/health", timeout=2)
            except HTTPError as error:
                if error.code == 429:
                    limited = True
                    break
        assert limited, "rate limit unexpectedly allowed all API requests"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
