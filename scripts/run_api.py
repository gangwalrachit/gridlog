#!/usr/bin/env python3
"""Run the GridLog FastAPI app under uvicorn."""

import logging

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx may leak query strings (including tokens) at INFO from any transitive client.
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    uvicorn.run("gridlog.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
