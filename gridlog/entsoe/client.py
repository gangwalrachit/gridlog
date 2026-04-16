"""ENTSO-E Transparency API HTTP client."""

from datetime import UTC, datetime

import httpx

from gridlog.config import settings


def _require_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware; got naive")
    return dt.astimezone(UTC)


class EntsoeClient:
    BASE_URL = "https://web-api.tp.entsoe.eu/api"
    DOCUMENT_TYPE_DAY_AHEAD = "A44"
    SE3_EIC = "10Y1001A1001A46L"

    def __init__(self, token: str | None = None, timeout: float = 60.0):
        # No base_url: httpx appends "/" to empty paths, and ENTSO-E 404s on /api/.
        self._client = httpx.Client(
            timeout=timeout,
            params={"securityToken": token or settings.entsoe_api_token},
        )

    def fetch_day_ahead(
        self,
        zone_eic: str,
        start: datetime,
        end: datetime,
    ) -> bytes:
        """Fetch day-ahead prices for a zone and UTC window; returns raw XML bytes."""
        start = _require_utc(start)
        end = _require_utc(end)
        response = self._client.get(
            self.BASE_URL,
            params={
                "documentType": self.DOCUMENT_TYPE_DAY_AHEAD,
                "in_Domain": zone_eic,
                "out_Domain": zone_eic,
                "periodStart": start.strftime("%Y%m%d%H%M"),
                "periodEnd": end.strftime("%Y%m%d%H%M"),
            },
        )
        response.raise_for_status()
        return response.content

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
