"""Parse ENTSO-E A44 day-ahead XML into VERSIONED DataFrame rows."""

from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree as ET

import pandas as pd

NS = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
_COLUMNS = ["knowledge_time", "valid_time", "value"]


def _parse_iso_duration(s: str) -> timedelta:
    """ISO 8601 duration subset: PT<N>M or PT<N>H."""
    if s.startswith("PT") and s.endswith("M"):
        return timedelta(minutes=int(s[2:-1]))
    if s.startswith("PT") and s.endswith("H"):
        return timedelta(hours=int(s[2:-1]))
    raise ValueError(f"unsupported ISO duration: {s!r}")


def _parse_utc(s: str) -> datetime:
    """Parse ENTSO-E timestamp (e.g. '2026-04-12T22:00Z') as UTC-aware."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def _typed(df: pd.DataFrame) -> pd.DataFrame:
    df["knowledge_time"] = pd.to_datetime(df["knowledge_time"], utc=True)
    df["valid_time"] = pd.to_datetime(df["valid_time"], utc=True)
    df["value"] = df["value"].astype("float64")
    return df


def parse_day_ahead(raw: bytes, knowledge_time: datetime) -> pd.DataFrame:
    """Parse A44 document → (knowledge_time, valid_time, value) rows.

    ENTSO-E A03 curves compress consecutive equal prices: missing positions
    carry the most recent explicit value forward.
    """
    root = ET.fromstring(raw)
    rows: list[tuple[datetime, datetime, float]] = []

    for period in root.findall(f".//{{{NS}}}TimeSeries/{{{NS}}}Period"):
        start = _parse_utc(period.findtext(f"{{{NS}}}timeInterval/{{{NS}}}start"))
        end = _parse_utc(period.findtext(f"{{{NS}}}timeInterval/{{{NS}}}end"))
        resolution = _parse_iso_duration(period.findtext(f"{{{NS}}}resolution"))
        slots = int((end - start) / resolution)

        explicit: dict[int, float] = {
            int(p.findtext(f"{{{NS}}}position")): float(p.findtext(f"{{{NS}}}price.amount"))
            for p in period.findall(f"{{{NS}}}Point")
        }
        if 1 not in explicit:
            raise ValueError("Period missing position 1; nothing to forward-fill from")
        if explicit and max(explicit) > slots:
            raise ValueError(f"Point position {max(explicit)} exceeds slot count {slots}")

        last = explicit[1]
        for pos in range(1, slots + 1):
            last = explicit.get(pos, last)
            rows.append((knowledge_time, start + (pos - 1) * resolution, last))

    if not rows:
        return _typed(pd.DataFrame(columns=_COLUMNS))
    return _typed(pd.DataFrame(rows, columns=_COLUMNS))
