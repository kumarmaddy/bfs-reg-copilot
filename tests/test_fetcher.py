"""Tests for the register-gated fetcher. No test touches the network: httpx.MockTransport only."""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
import yaml

from bfs_reg_copilot.ingest import (
    USER_AGENT,
    FetchError,
    FetchRefused,
    PoliteFetcher,
    require_ingestible,
)
from bfs_reg_copilot.registry import Register, Source, load_register

REGISTER_PATH = Path(__file__).resolve().parents[1] / "data" / "sources" / "register.yaml"
PAGE = b"<html><h1>Guideline</h1></html>"

Handler = Callable[[httpx.Request], httpx.Response]


class FakeClock:
    """Deterministic time: sleeping advances the clock instead of waiting."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(scope="module")
def register() -> Register:
    return load_register(REGISTER_PATH)


@pytest.fixture
def source(register: Register) -> Source:
    return register.ingestible()[0]


@pytest.fixture
def host(source: Source) -> str:
    hostname = urlsplit(str(source.url)).hostname
    assert hostname is not None
    return hostname


def _handler(
    *, robots: httpx.Response | None = None, page: httpx.Response | None = None
) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return robots if robots is not None else httpx.Response(404)
        return page if page is not None else httpx.Response(200, content=PAGE)

    return handle


def _fetcher(
    register: Register, handler: Handler, **kwargs: Any
) -> tuple[PoliteFetcher, FakeClock]:
    clock = FakeClock()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = PoliteFetcher(
        register, client=client, sleep=clock.sleep, monotonic=clock.monotonic, **kwargs
    )
    return fetcher, clock


# -- the register gate -------------------------------------------------------------------


def test_ingestible_source_is_allowed(register: Register, source: Source) -> None:
    assert require_ingestible(register, source.id).id == source.id


def test_unknown_source_is_refused(register: Register) -> None:
    with pytest.raises(FetchRefused, match="not in the register"):
        require_ingestible(register, "A-NOPE-NOTHING")


def test_pending_source_is_refused(register: Register) -> None:
    pending_id = register.pending[0].id
    with pytest.raises(FetchRefused, match="pending"):
        require_ingestible(register, pending_id)


def test_blocked_source_is_refused_with_its_reason(source: Source) -> None:
    raw = yaml.safe_load(REGISTER_PATH.read_text(encoding="utf-8"))
    blocked = copy.deepcopy(next(s for s in raw["sources"] if s["id"] == source.id))
    blocked["ingest_allowed"] = False
    blocked["blocking_reason"] = "terms not yet verified"
    raw["sources"] = [blocked]
    raw["pending"] = []
    register = Register.model_validate(raw)
    with pytest.raises(FetchRefused, match="terms not yet verified"):
        require_ingestible(register, source.id)


def test_refused_source_makes_no_network_call(register: Register) -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    fetcher, _ = _fetcher(register, handle)
    with pytest.raises(FetchRefused):
        fetcher.fetch(register.pending[0].id)
    assert calls == []


# -- a normal fetch ------------------------------------------------------------------------


def test_fetch_returns_body_and_lineage_metadata(register: Register, source: Source) -> None:
    page = httpx.Response(200, content=PAGE, headers={"content-type": "text/html", "etag": '"abc"'})
    fetcher, _ = _fetcher(register, _handler(page=page))
    result = fetcher.fetch(source.id)
    assert result.body == PAGE
    assert result.source_id == source.id
    assert result.final_url == str(source.url)
    assert result.content_type == "text/html"
    assert result.etag == '"abc"'
    offset = result.retrieved_at.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


def test_requests_identify_the_project(register: Register, source: Source) -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return httpx.Response(404) if request.url.path == "/robots.txt" else httpx.Response(200)

    fetcher, _ = _fetcher(register, handle)
    fetcher.fetch(source.id)
    assert seen
    assert all(ua == USER_AGENT for ua in seen)
    assert "bfs-reg-copilot" in USER_AGENT


def test_non_200_is_an_error(register: Register, source: Source) -> None:
    fetcher, _ = _fetcher(register, _handler(page=httpx.Response(503)))
    with pytest.raises(FetchError, match="HTTP 503"):
        fetcher.fetch(source.id)


def test_network_failure_is_an_error(register: Register, source: Source) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectError("boom", request=request)

    fetcher, _ = _fetcher(register, handle)
    with pytest.raises(FetchError, match="failed"):
        fetcher.fetch(source.id)


# -- robots.txt ----------------------------------------------------------------------------


def test_robots_disallow_refuses_the_fetch(register: Register, source: Source) -> None:
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    fetcher, _ = _fetcher(register, _handler(robots=robots))
    with pytest.raises(FetchRefused, match=r"robots\.txt"):
        fetcher.fetch(source.id)


def test_robots_allow_permits_the_fetch(register: Register, source: Source) -> None:
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
    fetcher, _ = _fetcher(register, _handler(robots=robots))
    assert fetcher.fetch(source.id).body == PAGE


@pytest.mark.parametrize("status", [404, 410])
def test_missing_robots_means_no_rules(register: Register, source: Source, status: int) -> None:
    fetcher, _ = _fetcher(register, _handler(robots=httpx.Response(status)))
    assert fetcher.fetch(source.id).status_code == 200


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_unreadable_robots_means_do_not_fetch(
    register: Register, source: Source, status: int
) -> None:
    fetcher, _ = _fetcher(register, _handler(robots=httpx.Response(status)))
    with pytest.raises(FetchRefused, match="not fetching"):
        fetcher.fetch(source.id)


def test_robots_is_fetched_once_per_host(register: Register, source: Source) -> None:
    robots_calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            robots_calls.append(request.url.path)
            return httpx.Response(404)
        return httpx.Response(200, content=PAGE)

    fetcher, _ = _fetcher(register, handle)
    fetcher.fetch(source.id)
    fetcher.fetch(source.id)
    assert len(robots_calls) == 1


# -- redirects -----------------------------------------------------------------------------


def test_redirect_to_another_host_is_refused(register: Register, source: Source) -> None:
    page = httpx.Response(302, headers={"location": "https://evil.example.com/x"})
    fetcher, _ = _fetcher(register, _handler(page=page))
    with pytest.raises(FetchRefused, match="leaves the registered host"):
        fetcher.fetch(source.id)


def test_redirect_to_http_is_refused(register: Register, source: Source, host: str) -> None:
    page = httpx.Response(301, headers={"location": f"http://{host}/plain"})
    fetcher, _ = _fetcher(register, _handler(page=page))
    with pytest.raises(FetchRefused, match="non-https"):
        fetcher.fetch(source.id)


def test_redirect_on_same_host_is_followed(register: Register, source: Source, host: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/moved":
            return httpx.Response(200, content=PAGE)
        return httpx.Response(301, headers={"location": f"https://{host}/moved"})

    fetcher, _ = _fetcher(register, handle)
    result = fetcher.fetch(source.id)
    assert result.final_url == f"https://{host}/moved"
    assert result.requested_url == str(source.url)


def test_redirect_loop_is_an_error(register: Register, source: Source, host: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": f"https://{host}/again"})

    fetcher, _ = _fetcher(register, handle, max_redirects=3)
    with pytest.raises(FetchError, match="redirects"):
        fetcher.fetch(source.id)


# -- size and rate limits ------------------------------------------------------------------


def test_oversized_body_is_an_error(register: Register, source: Source) -> None:
    fetcher, _ = _fetcher(
        register, _handler(page=httpx.Response(200, content=b"x" * 100)), max_bytes=10
    )
    with pytest.raises(FetchError, match="limit"):
        fetcher.fetch(source.id)


def test_declared_oversize_is_refused_before_reading(register: Register, source: Source) -> None:
    page = httpx.Response(200, content=b"x", headers={"content-length": "999999999"})
    fetcher, _ = _fetcher(register, _handler(page=page), max_bytes=1000)
    with pytest.raises(FetchError, match="declares"):
        fetcher.fetch(source.id)


def test_requests_to_one_host_are_spaced(register: Register, source: Source) -> None:
    fetcher, clock = _fetcher(register, _handler(), min_delay_s=2.0)
    fetcher.fetch(source.id)
    fetcher.fetch(source.id)
    # robots.txt then page (wait 2), then page again (wait 2)
    assert clock.sleeps == pytest.approx([2.0, 2.0])


def test_no_wait_when_enough_time_has_passed(register: Register, source: Source) -> None:
    fetcher, clock = _fetcher(register, _handler(), min_delay_s=2.0)
    fetcher.fetch(source.id)
    clock.now += 60
    clock.sleeps.clear()
    fetcher.fetch(source.id)
    assert clock.sleeps == []
