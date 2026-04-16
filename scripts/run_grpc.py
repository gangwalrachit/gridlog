#!/usr/bin/env python3
"""Run the GridLog gRPC server."""

import logging

from gridlog.grpc_service import serve

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# Silence any transitive httpx chatter that might leak query strings at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    logging.getLogger(__name__).info("gRPC server listening on 127.0.0.1:50051")
    serve()


if __name__ == "__main__":
    main()
