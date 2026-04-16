#!/usr/bin/env python3
"""Show the time-of-knowledge revision history for SE3's day-ahead window."""

from datetime import UTC, datetime, timedelta

from gridlog.query import get_price_revisions, get_prices_as_of

ZONE = "SE3"
SLOTS_TO_SHOW = 5


def main() -> None:
    today = datetime.now(UTC).date()
    delivery = today - timedelta(days=1)
    start = datetime(delivery.year, delivery.month, delivery.day, 0, 0, tzinfo=UTC) - timedelta(hours=2)
    end = start + timedelta(days=1)

    revisions = get_price_revisions(ZONE, start, end)
    if revisions.empty:
        print(f"No revisions stored for {ZONE} {start} → {end}. Run scripts/run_ingest.py first.")
        return

    knowledge_times = sorted(revisions.index.get_level_values("knowledge_time").unique())

    print(f"=== Revision ledger — {ZONE} day-ahead, {start.isoformat()} → {end.isoformat()} ===")
    print(f"{'knowledge_time':<36} {'rows':>6} {'unique values':>15}")
    for kt in knowledge_times:
        slice_ = revisions.xs(kt, level="knowledge_time")
        print(f"{kt.isoformat():<36} {len(slice_):>6} {slice_['value'].nunique():>15}")
    print()

    print(f"=== As-of comparison (first {SLOTS_TO_SHOW} slots) ===")
    header = f"{'valid_time (UTC)':<26}" + "".join(f"{kt.strftime('%m-%d %H:%M:%S'):>18}" for kt in knowledge_times) + "  DIFF?"
    print(header)

    as_of_frames = {kt: get_prices_as_of(ZONE, start, end, kt) for kt in knowledge_times}
    first_kt = knowledge_times[0]
    valid_times = list(as_of_frames[first_kt].index[:SLOTS_TO_SHOW])

    for vt in valid_times:
        row = [f"{vt.isoformat():<26}"]
        values = [as_of_frames[kt].loc[vt, "value"] for kt in knowledge_times]
        for v in values:
            row.append(f"{v:>18.2f}")
        diff = "yes" if len(set(values)) > 1 else "no"
        row.append(f"  {diff}")
        print("".join(row))


if __name__ == "__main__":
    main()
