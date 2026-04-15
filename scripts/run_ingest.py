#!/usr/bin/env python3
"""One-shot: fetch SE3 day-ahead for yesterday's delivery day and store."""

import logging
from datetime import UTC, datetime, timedelta

from gridlog.entsoe import EntsoeClient
from gridlog.ingest import fetch_and_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs request URLs at INFO, including ENTSO-E's securityToken in the query string.
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    today = datetime.now(UTC).date()
    delivery = today - timedelta(days=1)
    start = datetime(delivery.year, delivery.month, delivery.day, 0, 0, tzinfo=UTC) - timedelta(hours=2)
    end = start + timedelta(days=1)

    fetch_and_store(
        zone_name="SE3",
        zone_eic=EntsoeClient.SE3_EIC,
        start=start,
        end=end,
    )


if __name__ == "__main__":
    main()
