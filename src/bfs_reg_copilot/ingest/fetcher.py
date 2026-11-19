"""Register-gated, polite HTTP fetching.

Phase 1, slice 1.1. This module decides whether a source may be fetched and, if so, fetches it
politely and returns the bytes with metadata. It does not write to disk (slice 1.2) and does not
parse content (slice 1.3).

Rules, in the order they are applied:

1. The source must be in the register with ``ingest_allowed`` true. Blocked, pending and unknown
   ids are refused before any network call.
2. Every request, including redirects, must use https and stay on the host of the registered URL.
3. ``robots.txt`` must allow the path. Only a 404 or 410 on ``robots.txt`` means "no rules"; any
   other failure to read it is treated as "do not fetch".
4. Requests to one host are spaced at least ``min_delay_s`` apart.
5. The request identifies this project, and the body is size-limited.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from bfs_reg_copilot import __version__
from bfs_reg_copilot.registry import Register, Source

log = logging.getLogger(__name__)

AGENT_NAME = "bfs-reg-copilot"
USER_AGENT = (
    f"{AGENT_NAME}/{__version__} "
    "(learning project, public data only; +https://github.com/kumarmaddy/bfs-reg-copilot)"
)

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_ROBOTS_ABSENT_CODES = frozenset({404, 410})


class FetchRefused(Exception):
    """We chose not to fetch. The reason is in the message."""


class FetchError(Exception):
    """We tried to fetch and it failed (network, HTTP status, size, redirects)."""


@dataclass(frozen=True)
class FetchResult:
    """What one successful fetch returned, with enough metadata for lineage."""

    source_id: str
    requested_url: str
    final_url: str
    status_code: int
    content_type: str | None
    body: bytes
    retrieved_at: datetime  # timezone-aware, UTC
    etag: str | None
    last_modified: str | None


def require_ingestible(register: Register, source_id: str) -> Source:
    """Return the source if the register allows ingesting it; otherwise raise FetchRefused."""
    for source in register.sources:
        if source.id == source_id:
            if not source.ingest_allowed:
                reason = source.blocking_reason.strip()
                msg = f"{source_id} is blocked in the register: {reason}"
                raise FetchRefused(msg)
            return source
    if any(pending.id == source_id for pending in register.pending):
        msg = f"{source_id} is still pending verification in the register"
        raise FetchRefused(msg)
    msg = f"{source_id} is not in the register"
    raise FetchRefused(msg)


class PoliteFetcher:
    """Fetches registered sources, one at a time, following the rules in the module docstring."""

    def __init__(
        self,
        register: Register,
        *,
        client: httpx.Client | None = None,
        min_delay_s: float = 2.0,
        max_bytes: int = 20_000_000,
        timeout_s: float = 30.0,
        max_redirects: int = 5,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._register = register
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(follow_redirects=False)
        self._min_delay_s = min_delay_s
        self._max_bytes = max_bytes
        self._timeout_s = timeout_s
        self._max_redirects = max_redirects
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now if now is not None else (lambda: datetime.now(UTC))
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser] = {}

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self, source_id: str) -> FetchResult:
        """Fetch one registered source. Raises FetchRefused or FetchError, never partial data."""
        source = require_ingestible(self._register, source_id)
        url = str(source.url)
        host = _host_of(url)
        final_url, response, body = self._get_following(url, host)
        if response.status_code != 200:
            msg = f"{source_id}: HTTP {response.status_code} from {final_url}"
            raise FetchError(msg)
        log.info("fetched %s (%d bytes) from %s", source_id, len(body), final_url)
        return FetchResult(
            source_id=source_id,
            requested_url=url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            body=body,
            retrieved_at=self._now(),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )

    # -- internals -----------------------------------------------------------------------

    def _get_following(
        self, url: str, host: str, *, check_robots: bool = True
    ) -> tuple[str, httpx.Response, bytes]:
        """GET with manual redirect handling. Every hop is re-checked against the rules."""
        current = url
        for _ in range(self._max_redirects + 1):
            _check_same_host(current, host)
            if check_robots and not self._robots_allow(current, host):
                msg = f"robots.txt on {host} disallows {current}"
                raise FetchRefused(msg)
            response, body = self._get(current, host)
            if response.status_code in _REDIRECT_CODES:
                location = response.headers.get("location")
                if not location:
                    msg = f"redirect from {current} without a Location header"
                    raise FetchError(msg)
                current = urljoin(current, location)
                continue
            return current, response, body
        msg = f"more than {self._max_redirects} redirects starting at {url}"
        raise FetchError(msg)

    def _get(self, url: str, host: str) -> tuple[httpx.Response, bytes]:
        self._wait(host)
        try:
            with self._client.stream(
                "GET", url, headers={"User-Agent": USER_AGENT}, timeout=self._timeout_s
            ) as response:
                declared = response.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > self._max_bytes:
                    msg = f"{url} declares {declared} bytes, above the {self._max_bytes} limit"
                    raise FetchError(msg)
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self._max_bytes:
                        msg = f"{url} exceeded the {self._max_bytes} byte limit"
                        raise FetchError(msg)
                    chunks.append(chunk)
                return response, b"".join(chunks)
        except httpx.HTTPError as exc:
            msg = f"request to {url} failed: {exc}"
            raise FetchError(msg) from exc

    def _wait(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = self._min_delay_s - (self._monotonic() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._monotonic()

    def _robots_allow(self, url: str, host: str) -> bool:
        parser = self._robots.get(host)
        if parser is None:
            parser = self._load_robots(host)
            self._robots[host] = parser
        return parser.can_fetch(AGENT_NAME, url)

    def _load_robots(self, host: str) -> RobotFileParser:
        robots_url = f"https://{host}/robots.txt"
        parser = RobotFileParser()
        try:
            _, response, body = self._get_following(robots_url, host, check_robots=False)
        except FetchError as exc:
            msg = f"could not read robots.txt for {host}, so not fetching: {exc}"
            raise FetchRefused(msg) from exc
        if response.status_code == 200:
            parser.parse(body.decode("utf-8", errors="replace").splitlines())
        elif response.status_code in _ROBOTS_ABSENT_CODES:
            parser.parse([])  # no rules published
        else:
            msg = f"robots.txt for {host} returned HTTP {response.status_code}, so not fetching"
            raise FetchRefused(msg)
        return parser


def _host_of(url: str) -> str:
    host = urlsplit(url).hostname
    if not host:
        msg = f"URL has no host: {url}"
        raise FetchRefused(msg)
    return host


def _check_same_host(url: str, allowed_host: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        msg = f"refusing non-https URL: {url}"
        raise FetchRefused(msg)
    if parts.hostname != allowed_host:
        msg = f"refusing {url}: it leaves the registered host {allowed_host}"
        raise FetchRefused(msg)
