#!/usr/bin/env python3
"""One-shot: fetch SE3 day-ahead for the next published delivery day and store."""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from gridlog.entsoe import EntsoeClient
from gridlog.ingest import fetch_and_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs request URLs at INFO, including ENTSO-E's securityToken in the query string.
logging.getLogger("httpx").setLevel(logging.WARNING)

_CET = ZoneInfo("Europe/Stockholm")


def _target_window() -> tuple[datetime, datetime]:
    """Return the UTC window for the freshest published SE3 day-ahead delivery day.

    The Nord Pool day-ahead auction clears around 13:00 CET. After that,
    tomorrow's prices are published and available. Before that, today's prices
    (settled at yesterday's auction) are the freshest available.
    """
    now_cet = datetime.now(_CET)
    if now_cet.hour >= 13:
        delivery_date = (now_cet + timedelta(days=1)).date()
    else:
        delivery_date = now_cet.date()
    start = datetime(delivery_date.year, delivery_date.month, delivery_date.day, tzinfo=_CET).astimezone(UTC)
    return start, start + timedelta(hours=24)


def main() -> None:
    start, end = _target_window()
    fetch_and_store(
        zone_name="SE3",
        zone_eic=EntsoeClient.SE3_EIC,
        start=start,
        end=end,
    )


if __name__ == "__main__":
    main()
