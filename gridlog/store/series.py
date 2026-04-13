"""TimeDB wiring: initialize schema and register the day-ahead price series."""

import timedb as td

import gridlog.config  # noqa: F401  — sets TIMEDB_DSN in environment


def init_store() -> None:
    """Create TimeDB schema (idempotent). Reads connection from TIMEDB_DSN."""
    td.create(retention_short="6 months")


def ensure_series() -> None:
    """Register the SE3 day-ahead price series if not already present.

    TimeDB's get_series() returns a lazy collection even for missing series,
    so we can't probe existence that way. create_series() raises ValueError
    on the (name, labels) unique constraint — that's the real idempotency hook.
    """
    try:
        td.create_series(
            name="da_price",
            unit="EUR/MWh",
            labels={"zone": "SE3", "resolution": "PT1H"},
            description="ENTSO-E day-ahead hourly price for SE3",
            overlapping=True,
            retention="short",
        )
    except ValueError:
        pass
