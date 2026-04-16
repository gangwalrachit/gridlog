"""FastAPI surface over the GridLog query module."""

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_serializer

from gridlog.query import get_latest_prices, get_price_revisions, get_prices_as_of
from gridlog.store.series import SERIES_NAME

ALLOWED_ZONES = {"SE3"}


def _iso_z(dt: datetime) -> str:
    """Always serialize datetimes as UTC ISO-8601 with a trailing Z."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _require_utc(dt: datetime, field: str) -> datetime:
    if dt.tzinfo is None:
        raise HTTPException(status_code=400, detail=f"{field} must be timezone-aware")
    return dt.astimezone(UTC)


def _require_zone(zone: str) -> str:
    if zone not in ALLOWED_ZONES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown zone {zone!r}; allowed: {sorted(ALLOWED_ZONES)}",
        )
    return zone


class HealthResponse(BaseModel):
    status: str
    timedb: str


class PriceRow(BaseModel):
    valid_time: datetime
    value: float

    @field_serializer("valid_time")
    def _fmt_valid_time(self, dt: datetime) -> str:
        return _iso_z(dt)


class RevisionRow(BaseModel):
    valid_time: datetime
    knowledge_time: datetime
    value: float

    @field_serializer("valid_time", "knowledge_time")
    def _fmt_times(self, dt: datetime) -> str:
        return _iso_z(dt)


app = FastAPI(title="GridLog", description="Time-of-knowledge intraday price ledger")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    import timedb

    try:
        # Touching the series forces a Postgres round-trip through TimeDB.
        timedb.get_series(name=SERIES_NAME)
        return HealthResponse(status="ok", timedb="reachable")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"timedb unreachable: {e}")


@app.get("/prices/latest", response_model=list[PriceRow])
def latest(
    zone: str = Query(..., description="Bidding zone name, e.g. SE3"),
    start: datetime = Query(..., description="Window start, UTC ISO-8601"),
    end: datetime = Query(..., description="Window end (exclusive), UTC ISO-8601"),
) -> list[PriceRow]:
    zone = _require_zone(zone)
    start = _require_utc(start, "start")
    end = _require_utc(end, "end")

    df = get_latest_prices(zone, start, end).reset_index()
    return [PriceRow(valid_time=row.valid_time, value=row.value) for row in df.itertuples(index=False)]


@app.get("/prices/as-of", response_model=list[PriceRow])
def as_of(
    zone: str = Query(...),
    start: datetime = Query(...),
    end: datetime = Query(...),
    as_of: datetime = Query(..., description="Cutoff knowledge_time (inclusive), UTC ISO-8601"),
) -> list[PriceRow]:
    zone = _require_zone(zone)
    start = _require_utc(start, "start")
    end = _require_utc(end, "end")
    as_of = _require_utc(as_of, "as_of")

    df = get_prices_as_of(zone, start, end, as_of).reset_index()
    return [PriceRow(valid_time=row.valid_time, value=row.value) for row in df.itertuples(index=False)]


@app.get("/prices/revisions", response_model=list[RevisionRow])
def revisions(
    zone: str = Query(...),
    start: datetime = Query(...),
    end: datetime = Query(...),
) -> list[RevisionRow]:
    zone = _require_zone(zone)
    start = _require_utc(start, "start")
    end = _require_utc(end, "end")

    df = get_price_revisions(zone, start, end).reset_index()
    df = df.sort_values(["valid_time", "knowledge_time"])
    return [
        RevisionRow(valid_time=row.valid_time, knowledge_time=row.knowledge_time, value=row.value)
        for row in df.itertuples(index=False)
    ]
