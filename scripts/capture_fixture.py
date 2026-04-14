#!/usr/bin/env python3
"""Capture one SE3 day-ahead XML fixture for parser unit tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from gridlog.entsoe import EntsoeClient

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def main() -> None:
    # Yesterday's delivery day in UTC: [D-1 22:00, D 22:00) maps to SE3 local Apr D.
    today = datetime.now(UTC).date()
    delivery = today - timedelta(days=1)
    start = datetime(delivery.year, delivery.month, delivery.day, 0, 0, tzinfo=UTC) - timedelta(hours=2)
    end = start + timedelta(days=1)

    with EntsoeClient() as client:
        xml = client.fetch_day_ahead(client.SE3_EIC, start, end)

    out = FIXTURES_DIR / f"se3_da_{delivery.isoformat()}.xml"
    out.write_bytes(xml)
    print(f"Wrote {len(xml)} bytes → {out.relative_to(FIXTURES_DIR.parent)}")


if __name__ == "__main__":
    main()
