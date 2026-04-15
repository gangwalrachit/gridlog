"""End-to-end time-of-knowledge reads against a running TimeDB.

Writes to an isolated `test_price` series using per-run unique valid_time
windows, so production data is untouched and repeated runs never collide.
Marked `integration` — skipped by default, opt in with `pytest -m integration`.
"""

import random
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
import timedb

from gridlog.store.series import SERIES_NAME, init_store

TEST_ZONE = "TEST1"


def _series():
    return timedb.get_series(name=SERIES_NAME).where(zone=TEST_ZONE)


@pytest.fixture(scope="module")
def isolated_series():
    init_store()
    try:
        timedb.create_series(
            name=SERIES_NAME,
            unit="EUR/MWh",
            labels={"zone": TEST_ZONE, "resolution": "PT15M"},
            description="Integration test series",
            overlapping=True,
            retention="short",
        )
    except ValueError:
        pass
    return _series()


@pytest.fixture(scope="module")
def seeded(isolated_series):
    """Insert two batches at the same 4 valid_times with different knowledge_times."""
    now = datetime.now(UTC)
    # Random 1-hour anchor in a 100-year window → prior runs are effectively isolated.
    offset_hours = random.randint(0, 100 * 365 * 24)
    valid_start = datetime(2100, 1, 1, tzinfo=UTC) + timedelta(hours=offset_hours)
    valid_times = [valid_start + timedelta(minutes=15 * i) for i in range(4)]
    kt1 = now
    kt2 = now + timedelta(seconds=1)

    batch1 = pd.DataFrame({"valid_time": valid_times, "value": [10.0, 20.0, 30.0, 40.0]})
    isolated_series.insert(batch1, workflow_id="test", knowledge_time=kt1)

    batch2 = pd.DataFrame({"valid_time": valid_times, "value": [11.0, 21.0, 31.0, 41.0]})
    isolated_series.insert(batch2, workflow_id="test", knowledge_time=kt2)

    return {
        "start": valid_start,
        "end": valid_start + timedelta(hours=1),
        "kt1": kt1,
        "kt2": kt2,
    }


@pytest.mark.integration
def test_latest_returns_newest_batch(seeded):
    from gridlog.query.prices import get_latest_prices

    df = get_latest_prices(TEST_ZONE, seeded["start"], seeded["end"])

    assert len(df) == 4
    assert list(df["value"]) == [11.0, 21.0, 31.0, 41.0]


@pytest.mark.integration
def test_as_of_kt1_returns_first_batch(seeded):
    from gridlog.query.prices import get_prices_as_of

    cutoff = seeded["kt1"] + timedelta(microseconds=1)
    df = get_prices_as_of(TEST_ZONE, seeded["start"], seeded["end"], cutoff)

    assert len(df) == 4
    assert list(df["value"]) == [10.0, 20.0, 30.0, 40.0]


@pytest.mark.integration
def test_as_of_between_batches_returns_first_batch(seeded):
    from gridlog.query.prices import get_prices_as_of

    cutoff = seeded["kt1"] + (seeded["kt2"] - seeded["kt1"]) / 2
    df = get_prices_as_of(TEST_ZONE, seeded["start"], seeded["end"], cutoff)

    assert list(df["value"]) == [10.0, 20.0, 30.0, 40.0]


@pytest.mark.integration
def test_revisions_returns_both_batches(seeded):
    from gridlog.query.prices import get_price_revisions

    df = get_price_revisions(TEST_ZONE, seeded["start"], seeded["end"])

    assert len(df) == 8
    kts = df.index.get_level_values("knowledge_time").unique()
    assert set(kts) == {seeded["kt1"], seeded["kt2"]}
