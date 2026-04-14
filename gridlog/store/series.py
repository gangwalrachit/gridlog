"""TimeDB wiring: schema init and series registration."""

import timedb as td

import gridlog.config  # noqa: F401  — sets TIMEDB_DSN on import


def init_store() -> None:
    """Create TimeDB schema (idempotent)."""
    td.create(retention_short="6 months")


def ensure_series() -> None:
    """Register the SE3 day-ahead price series (idempotent via ValueError on duplicate)."""
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
