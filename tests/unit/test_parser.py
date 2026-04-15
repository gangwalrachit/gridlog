"""Fixture-driven unit tests for the ENTSO-E day-ahead parser."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from gridlog.entsoe.parser import parse_day_ahead

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "se3_da_2026-04-13.xml"
KT = datetime(2026, 4, 14, 17, 22, 7, tzinfo=UTC)

EMPTY_DOC = b"""<?xml version="1.0" encoding="utf-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <mRID>empty</mRID>
</Publication_MarketDocument>
"""

BAD_RESOLUTION_DOC = b"""<?xml version="1.0" encoding="utf-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries>
    <Period>
      <timeInterval><start>2026-04-12T22:00Z</start><end>2026-04-13T22:00Z</end></timeInterval>
      <resolution>P1D</resolution>
      <Point><position>1</position><price.amount>50.0</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""


def test_parses_se3_fixture_shape_and_dtypes():
    df = parse_day_ahead(FIXTURE.read_bytes(), KT)

    assert df.shape == (96, 3)
    assert list(df.columns) == ["knowledge_time", "valid_time", "value"]
    assert str(df["knowledge_time"].dtype).startswith("datetime64") and df["knowledge_time"].dt.tz is not None
    assert str(df["valid_time"].dtype).startswith("datetime64") and df["valid_time"].dt.tz is not None
    assert df["value"].dtype == "float64"


def test_parses_se3_fixture_values():
    df = parse_day_ahead(FIXTURE.read_bytes(), KT)

    # Single knowledge_time for the whole batch.
    assert df["knowledge_time"].nunique() == 1
    assert df["knowledge_time"].iloc[0] == KT

    # Period anchor and 15-min cadence with no gaps.
    assert df["valid_time"].iloc[0] == datetime(2026, 4, 12, 22, 0, tzinfo=UTC)
    assert df["valid_time"].iloc[-1] == datetime(2026, 4, 13, 21, 45, tzinfo=UTC)
    diffs = df["valid_time"].diff().dropna().unique()
    assert len(diffs) == 1 and diffs[0] == pd.Timedelta(minutes=15)

    # Spot-check first and last price from the raw XML.
    assert df["value"].iloc[0] == pytest.approx(47.1)
    assert df["value"].iloc[-1] == pytest.approx(38.86)


def test_empty_document_returns_empty_typed_frame():
    df = parse_day_ahead(EMPTY_DOC, KT)

    assert df.shape == (0, 3)
    assert list(df.columns) == ["knowledge_time", "valid_time", "value"]
    assert df["value"].dtype == "float64"


def test_unsupported_resolution_raises():
    with pytest.raises(ValueError, match="unsupported ISO duration"):
        parse_day_ahead(BAD_RESOLUTION_DOC, KT)
