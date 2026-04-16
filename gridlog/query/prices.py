"""Time-of-knowledge reads over the GridLog price series."""

from datetime import datetime, timedelta

import pandas as pd
import timedb

from gridlog.store.series import SERIES_NAME


def _series(zone_name: str):
    return timedb.get_series(name=SERIES_NAME).where(zone=zone_name)


def get_latest_prices(zone_name: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Return the latest-known price per valid_time in [start, end)."""
    return _series(zone_name).read(start_valid=start, end_valid=end)


def get_prices_as_of(
    zone_name: str,
    start: datetime,
    end: datetime,
    as_of: datetime,
) -> pd.DataFrame:
    """Return the price per valid_time in [start, end) as known at or before `as_of`."""
    # TimeDB's end_known is exclusive; offset by 1µs for inclusive "as of T" semantics.
    return _series(zone_name).read(
        start_valid=start,
        end_valid=end,
        end_known=as_of + timedelta(microseconds=1),
    )


def get_price_revisions(zone_name: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Return every revision in [start, end), indexed by (knowledge_time, valid_time)."""
    return _series(zone_name).read(start_valid=start, end_valid=end, versions=True)
