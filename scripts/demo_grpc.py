#!/usr/bin/env python3
"""Demonstrate all three gRPC RPCs against the current delivery window.

Spins the gRPC server up in a background thread — no separate terminal needed.
Run after at least one ingest:

    python scripts/demo_grpc.py
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from gridlog.grpc_service.generated import prices_pb2, prices_pb2_grpc
from gridlog.grpc_service.server import build_server

_CET = ZoneInfo("Europe/Stockholm")
_W = 62


def _dt_to_ts(dt: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt.astimezone(UTC))
    return ts


def _fmt(dt: datetime) -> str:
    return f"{dt.strftime('%b')} {dt.day} {dt.strftime('%H:%M')} UTC"


def _target_window() -> tuple[datetime, datetime]:
    """Same CET-auction-aware logic as run_ingest.py."""
    now_cet = datetime.now(_CET)
    if now_cet.hour >= 13:
        delivery_date = (now_cet + timedelta(days=1)).date()
    else:
        delivery_date = now_cet.date()
    start = datetime(
        delivery_date.year, delivery_date.month, delivery_date.day, tzinfo=_CET
    ).astimezone(UTC)
    return start, start + timedelta(hours=24)


def main() -> None:
    logging.disable(logging.CRITICAL)  # suppress server startup noise

    server, port = build_server(host="127.0.0.1", port=0)  # port=0 → random free port
    server.start()

    try:
        with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = prices_pb2_grpc.PriceServiceStub(channel)
            start, end = _target_window()

            print()
            print("═" * _W)
            print(f"  gRPC Demo  ·  SE3")
            print(f"  {start.strftime('%Y-%m-%dT%H:%MZ')} → {end.strftime('%Y-%m-%dT%H:%MZ')}")
            print("═" * _W)

            window = prices_pb2.PriceWindowRequest(
                zone="SE3", start=_dt_to_ts(start), end=_dt_to_ts(end)
            )

            # ── GetLatest ─────────────────────────────────────────────
            print("\n── GetLatest " + "─" * 48)
            latest = stub.GetLatest(window)
            if latest.rows:
                print(f"  {len(latest.rows)} rows  (one per 15-min delivery slot)")
                print()
                for r in latest.rows[:5]:
                    vt = r.valid_time.ToDatetime(tzinfo=UTC)
                    print(f"    {vt.strftime('%H:%M')}  {r.value:>8.2f} EUR/MWh")
                print(f"    ···  {len(latest.rows) - 5} more rows")
            else:
                print("  0 rows — run scripts/run_ingest.py first")

            # ── GetRevisions ──────────────────────────────────────────
            print("\n── GetRevisions " + "─" * 45)
            revisions = stub.GetRevisions(window)
            kt_counts: dict[datetime, int] = defaultdict(int)
            for r in revisions.rows:
                kt_counts[r.knowledge_time.ToDatetime(tzinfo=UTC)] += 1
            sorted_kts = sorted(kt_counts)

            if sorted_kts:
                print(f"  {len(revisions.rows)} rows  ·  {len(sorted_kts)} snapshot{'s' if len(sorted_kts) != 1 else ''}")
                print()
                for i, kt in enumerate(sorted_kts):
                    tag = "  ← latest" if i == len(sorted_kts) - 1 else ""
                    print(f"    {_fmt(kt)}  ·  {kt_counts[kt]} rows{tag}")
            else:
                print("  0 rows — run scripts/run_ingest.py first")

            # ── GetAsOf ───────────────────────────────────────────────
            print("\n── GetAsOf " + "─" * 50)
            if sorted_kts:
                first_kt = sorted_kts[0]
                cases = [
                    ("before", first_kt - timedelta(hours=1)),
                    ("after ", first_kt + timedelta(minutes=1)),
                ]
                for label, cutoff in cases:
                    resp = stub.GetAsOf(
                        prices_pb2.AsOfRequest(
                            zone="SE3",
                            start=_dt_to_ts(start),
                            end=_dt_to_ts(end),
                            as_of=_dt_to_ts(cutoff),
                        )
                    )
                    print(f"  as_of {label} first snapshot  ({_fmt(cutoff)})")
                    print(f"  → {len(resp.rows)} rows")
                    print()
                print("  Same delivery window. The knowledge cutoff changes everything.")
            else:
                print("  No revision data — run scripts/run_ingest.py first")

            print()
            print("═" * _W)
            print()

    finally:
        server.stop(grace=0)


if __name__ == "__main__":
    main()
