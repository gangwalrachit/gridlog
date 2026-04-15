"""Orchestrate one ENTSO-E fetch → parse → TimeDB insert cycle."""

import logging
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

import httpx
import timedb
from timedb.sdk import InsertResult

from gridlog.entsoe import EntsoeClient, parse_day_ahead
from gridlog.entsoe.parser import NS

logger = logging.getLogger(__name__)

WORKFLOW_ID = "entsoe_da_ingest"
SERIES_NAME = "da_price"


def _created_datetime(raw: bytes) -> str | None:
    """Extract <createdDateTime> for audit metadata; best-effort, returns None on failure."""
    try:
        root = ET.fromstring(raw)
        return root.findtext(f"{{{NS}}}createdDateTime")
    except ET.ParseError:
        return None


def fetch_and_store(
    zone_name: str,
    zone_eic: str,
    start: datetime,
    end: datetime,
) -> InsertResult | None:
    """Fetch one day-ahead window for a zone and insert into TimeDB.

    Returns the InsertResult on success, or None on transient fetch failure
    (WARN-and-skip: next cycle will pick up any revisions).
    """
    batch_start_time = datetime.now(UTC)
    knowledge_time = batch_start_time

    try:
        with EntsoeClient() as client:
            raw = client.fetch_day_ahead(zone_eic, start, end)
    except httpx.HTTPError as e:
        logger.warning(
            "ENTSO-E fetch failed for zone=%s window=[%s, %s): %s",
            zone_name, start.isoformat(), end.isoformat(), e,
        )
        return None

    df = parse_day_ahead(raw, knowledge_time)
    batch_finish_time = datetime.now(UTC)

    if df.empty:
        logger.warning(
            "ENTSO-E returned empty document for zone=%s window=[%s, %s); skipping insert",
            zone_name, start.isoformat(), end.isoformat(),
        )
        return None

    series = timedb.get_series(name=SERIES_NAME).where(zone=zone_name)
    result = series.insert(
        df[["valid_time", "value"]],
        workflow_id=WORKFLOW_ID,
        knowledge_time=knowledge_time,
        batch_start_time=batch_start_time,
        batch_finish_time=batch_finish_time,
        batch_params={
            "source": "entsoe_transparency_api",
            "document_type": "A44",
            "zone_eic": zone_eic,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "created_datetime": _created_datetime(raw),
            "bytes": len(raw),
            "rows": len(df),
        },
    )
    logger.info(
        "Inserted %d rows for zone=%s batch_id=%s knowledge_time=%s",
        len(df), zone_name, result.batch_id, knowledge_time.isoformat(),
    )
    return result
