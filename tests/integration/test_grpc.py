"""End-to-end gRPC reads against a running TimeDB through an in-process server.

Binds the server to a random port, connects a real grpc channel, and exercises
the three RPCs plus the unknown-zone error path. Reuses the random-anchor
isolation pattern from test_query.py. Marked `integration`.
"""

import random
from datetime import UTC, datetime, timedelta

import grpc
import pandas as pd
import pytest
import timedb
from google.protobuf.timestamp_pb2 import Timestamp

from gridlog.grpc_service.generated import prices_pb2, prices_pb2_grpc
from gridlog.grpc_service.server import ALLOWED_ZONES, build_server
from gridlog.store.series import SERIES_NAME, init_store

TEST_ZONE = "TEST1"


def _ts(dt: datetime) -> Timestamp:
    t = Timestamp()
    t.FromDatetime(dt.astimezone(UTC))
    return t


@pytest.fixture(scope="module", autouse=True)
def _allow_test_zone():
    ALLOWED_ZONES.add(TEST_ZONE)
    yield
    ALLOWED_ZONES.discard(TEST_ZONE)


@pytest.fixture(scope="module")
def stub():
    server, port = build_server(port=0)
    server.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    yield prices_pb2_grpc.PriceServiceStub(channel)
    channel.close()
    server.stop(grace=0)


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
        "start": valid_start,
        "end": valid_start + timedelta(hours=1),
        "kt1": kt1,
        "kt2": kt2,
    }


@pytest.mark.integration
def test_get_latest(stub, seeded):
    resp = stub.GetLatest(
        prices_pb2.PriceWindowRequest(
            zone=TEST_ZONE, start=_ts(seeded["start"]), end=_ts(seeded["end"])
        )
    )
    assert [r.value for r in resp.rows] == [11.0, 21.0, 31.0, 41.0]


@pytest.mark.integration
def test_get_as_of_kt1(stub, seeded):
    resp = stub.GetAsOf(
        prices_pb2.AsOfRequest(
            zone=TEST_ZONE,
            start=_ts(seeded["start"]),
            end=_ts(seeded["end"]),
            as_of=_ts(seeded["kt1"]),
        )
    )
    assert [r.value for r in resp.rows] == [10.0, 20.0, 30.0, 40.0]


@pytest.mark.integration
def test_get_revisions_sorted(stub, seeded):
    resp = stub.GetRevisions(
        prices_pb2.PriceWindowRequest(
            zone=TEST_ZONE, start=_ts(seeded["start"]), end=_ts(seeded["end"])
        )
    )
    assert len(resp.rows) == 8
    pairs = [(r.valid_time.ToNanoseconds(), r.knowledge_time.ToNanoseconds()) for r in resp.rows]
    assert pairs == sorted(pairs)


@pytest.mark.integration
def test_unknown_zone_returns_invalid_argument(stub, seeded):
    with pytest.raises(grpc.RpcError) as exc:
        stub.GetLatest(
            prices_pb2.PriceWindowRequest(
                zone="NOPE", start=_ts(seeded["start"]), end=_ts(seeded["end"])
            )
        )
    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
