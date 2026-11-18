"""Entry point for the S4 path proxy container."""
from __future__ import annotations

import logging
import os

from aiohttp import web
from s4_path_proxy.proxy import create_app

LOG = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    host = os.environ.get("S4_PROXY_HOST", "0.0.0.0")
    port = int(os.environ.get("S4_PROXY_PORT", "7480"))
    app = create_app()
    web.run_app(app, host=host, port=port, access_log=LOG)


if __name__ == "__main__":
    main()
