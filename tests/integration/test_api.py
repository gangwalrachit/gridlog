"""End-to-end HTTP reads against a running TimeDB through the FastAPI app.

Reuses the same random-anchor isolation pattern as test_query.py — a
fresh 100-year-future window per module run, seeded with two batches at
distinct knowledge_times. Marked `integration` — opt in with
`pytest -m integration`.
"""

import random
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
import timedb
from fastapi.testclient import TestClient

from gridlog.api.app import ALLOWED_ZONES, app
from gridlog.store.series import SERIES_NAME, init_store

TEST_ZONE = "TEST1"


@pytest.fixture(scope="module", autouse=True)
def _allow_test_zone():
    ALLOWED_ZONES.add(TEST_ZONE)
    yield
    ALLOWED_ZONES.discard(TEST_ZONE)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def seeded():
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

    series = timedb.get_series(name=SERIES_NAME).where(zone=TEST_ZONE)

    now = datetime.now(UTC)
    offset_hours = random.randint(0, 100 * 365 * 24)
    valid_start = datetime(2100, 1, 1, tzinfo=UTC) + timedelta(hours=offset_hours)
    valid_times = [valid_start + timedelta(minutes=15 * i) for i in range(4)]
    kt1 = now
    kt2 = now + timedelta(seconds=1)

    series.insert(
        pd.DataFrame({"valid_time": valid_times, "value": [10.0, 20.0, 30.0, 40.0]}),
        workflow_id="test",
        knowledge_time=kt1,
    )
    series.insert(
        pd.DataFrame({"valid_time": valid_times, "value": [11.0, 21.0, 31.0, 41.0]}),
        workflow_id="test",
        knowledge_time=kt2,
    )

    return {
        "start": valid_start.isoformat(),
        "end": (valid_start + timedelta(hours=1)).isoformat(),
        "kt1": kt1.isoformat(),
        "kt2": kt2.isoformat(),
    }


@pytest.mark.integration
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["timedb"] == "reachable"


@pytest.mark.integration
def test_latest(client, seeded):
    r = client.get("/prices/latest", params={"zone": TEST_ZONE, "start": seeded["start"], "end": seeded["end"]})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 4
    assert [row["value"] for row in rows] == [11.0, 21.0, 31.0, 41.0]
    assert all(row["valid_time"].endswith("Z") for row in rows)


@pytest.mark.integration
def test_as_of_kt1(client, seeded):
    r = client.get(
        "/prices/as-of",
        params={"zone": TEST_ZONE, "start": seeded["start"], "end": seeded["end"], "as_of": seeded["kt1"]},
    )
    assert r.status_code == 200
    rows = r.json()
    assert [row["value"] for row in rows] == [10.0, 20.0, 30.0, 40.0]


@pytest.mark.integration
def test_revisions_sorted_by_valid_then_knowledge(client, seeded):
    r = client.get(
        "/prices/revisions",
        params={"zone": TEST_ZONE, "start": seeded["start"], "end": seeded["end"]},
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 8

    # Same valid_time should appear consecutively, kt1 before kt2.
    pairs = [(row["valid_time"], row["knowledge_time"]) for row in rows]
    assert pairs == sorted(pairs)
    vts = [p[0] for p in pairs]
    assert vts[0] == vts[1] and vts[2] == vts[3]


@pytest.mark.integration
def test_unknown_zone_returns_400(client, seeded):
    r = client.get("/prices/latest", params={"zone": "NOPE", "start": seeded["start"], "end": seeded["end"]})
    assert r.status_code == 400


@pytest.mark.integration
def test_naive_datetime_returns_400(client):
    r = client.get(
        "/prices/latest",
        params={"zone": TEST_ZONE, "start": "2100-01-01T00:00:00", "end": "2100-01-01T01:00:00"},
    )
    assert r.status_code == 400
