"""Run the API: `uv run python -m bfs_reg_copilot.api`. Local only unless told otherwise."""

from __future__ import annotations

import argparse
import ipaddress
import logging
import sys

from bfs_reg_copilot.api.app import create_app
from bfs_reg_copilot.api.backend import DEPENDENCY_ERRORS, build_backend
from bfs_reg_copilot.api.service import AnswerService

EXIT_OK = 0
EXIT_REFUSED = 2


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bfs_reg_copilot.api", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow a non-local address. The API has no authentication yet: do not use this on a "
        "shared network.",
    )
    args = parser.parse_args(argv)
    if not is_loopback(args.host) and not args.allow_remote:
        print(
            f"refusing to listen on {args.host}: the API has no authentication. "
            "Use 127.0.0.1, or pass --allow-remote if you accept that."
        )
        return EXIT_REFUSED
    import uvicorn  # imported late so `--help` and the host check work without the server

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = create_app(AnswerService(build_backend, DEPENDENCY_ERRORS))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
