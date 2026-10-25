"""Elexon BMRS Insights API client (verified contract from Phase 1).

Endpoints (base https://data.elexon.co.uk/bmrs/api/v1):
  GET /datasets/FUELHH/stream  params: settlementDateFrom, settlementDateTo, fuelType
  GET /datasets/WINDFOR/stream params: publishDateTimeFrom, publishDateTimeTo
  GET /balancing/pricing/market-index params: From, To, dataProviders=APXMIDP

Verified notes enforced here:
  * No pagination exists - one response carries every row (18k rows observed).
  * FUELHH rejects mixing settlement and publish date filters (HTTP 400).
  * Timestamps are ISO-8601 UTC with a trailing 'Z'.
  * fuelType server-side filter is applied and re-checked client-side; an
    unknown fuelType returns HTTP 200 with [] upstream, so values are
    validated before the request (see app.core.config.normalize_fuel_type).
  * market-index returns {"metadata": ..., "data": [...]} (not a bare array)
    and caps a single request at 7 days, so longer ranges are chunked.
    The To bound is inclusive at 00:00, so a chunk To must be one day after
    the last settlement date that needs covering.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from app.core.config import Settings, normalize_fuel_type
from app.models.records import ActualRow, ForecastRow, PriceRow

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Day-ahead mid price provider used for the indicative £ valuation.
PRICE_PROVIDER = "APXMIDP"
# Verified upstream limit: one market-index request may span at most 7 days.
PRICE_MAX_RANGE_DAYS = 7


class ElexonError(Exception):
    """Base class for upstream Elexon failures."""


class ElexonTransportError(ElexonError):
    """Timeouts, connection failures."""


class ElexonHTTPError(ElexonError):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        super().__init__(f"Elexon API returned HTTP {status_code}: {body[:300]}")


class ElexonSchemaError(ElexonError):
    """Malformed response body or missing required fields."""


def parse_utc(value: object, field: str) -> datetime:
    """Strictly parse an Elexon UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)."""
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ElexonSchemaError(f"field '{field}' is not an ISO UTC timestamp: {value!r}")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ElexonSchemaError(f"field '{field}' has unparseable timestamp: {value!r}") from exc


def _require(item: dict, key: str) -> object:
    if key not in item:
        raise ElexonSchemaError(f"response row is missing required field '{key}': {item!r}")
    return item[key]


def _generation(item: dict) -> float | None:
    raw = item.get("generation")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ElexonSchemaError(f"field 'generation' is not numeric: {raw!r}")
    return float(raw)


class ElexonClient:
    def __init__(self, settings: Settings, transport: httpx.Client | None = None):
        self.settings = settings
        self._transport = transport
        self._mock_client: httpx.Client | None = None

    # -- low level ---------------------------------------------------------
    def _get(self, path: str, params: dict) -> object:
        url = f"{self.settings.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(1, self.settings.http_retries + 1):
            try:
                if self._transport is not None:
                    if self._mock_client is None:
                        self._mock_client = httpx.Client(
                            transport=self._transport,
                            timeout=self.settings.http_timeout_seconds,
                        )
                    response = self._mock_client.get(url, params=params)
                else:
                    with httpx.Client(timeout=self.settings.http_timeout_seconds) as client:
                        response = client.get(url, params=params)
            except httpx.TimeoutException as exc:
                last_error = ElexonTransportError(f"timeout calling {path}")
                logger.warning("attempt %s/%s timeout: %s", attempt, self.settings.http_retries, exc)
                time.sleep(0.3 * attempt)
                continue
            except httpx.HTTPError as exc:
                last_error = ElexonTransportError(f"transport failure calling {path}: {exc}")
                logger.warning("attempt %s/%s transport error: %s", attempt, self.settings.http_retries, exc)
                time.sleep(0.3 * attempt)
                continue

            if response.status_code in RETRYABLE_STATUS:
                last_error = ElexonHTTPError(response.status_code, response.text)
                logger.warning("attempt %s/%s HTTP %s from %s", attempt, self.settings.http_retries,
                               response.status_code, path)
                time.sleep(0.3 * attempt)
                continue
            if response.status_code >= 400:
                raise ElexonHTTPError(response.status_code, response.text)
            try:
                return response.json()
            except ValueError as exc:
                raise ElexonSchemaError(f"response from {path} is not valid JSON") from exc
        assert last_error is not None
        raise last_error

    # -- FUELHH ------------------------------------------------------------
    def fetch_actuals(
        self, start: date, end: date, fuel_type: str | None = None
    ) -> list[ActualRow]:
        """Half-hourly outturn for the inclusive settlement-date range.

        fuel_type defaults to the configured FUEL_TYPE (WIND unless overridden).
        """
        fuel = normalize_fuel_type(fuel_type or self.settings.fuel_type)
        payload = self._get(
            "/datasets/FUELHH/stream",
            {
                "settlementDateFrom": start.isoformat(),
                "settlementDateTo": end.isoformat(),
                "fuelType": fuel,
            },
        )
        items = self._rows(payload, "FUELHH")
        rows: list[ActualRow] = []
        for item in items:
            if item.get("fuelType") != fuel:  # server-side filter, re-checked here
                continue
            settlement_date = _require(item, "settlementDate")
            period = _require(item, "settlementPeriod")
            if not isinstance(settlement_date, str):
                raise ElexonSchemaError(f"settlementDate is not a string: {settlement_date!r}")
            if isinstance(period, bool) or not isinstance(period, int):
                raise ElexonSchemaError(f"settlementPeriod is not an integer: {period!r}")
            rows.append(
                ActualRow(
                    settlement_date=date.fromisoformat(settlement_date),
                    settlement_period=period,
                    start_time=parse_utc(_require(item, "startTime"), "startTime"),
                    publish_time=parse_utc(_require(item, "publishTime"), "publishTime"),
                    generation_mw=_generation(item),
                )
            )
        return rows

    # -- WINDFOR -----------------------------------------------------------
    def fetch_forecasts(self, publish_from: datetime, publish_to: datetime) -> list[ForecastRow]:
        """All WINDFOR vintages published in the inclusive datetime range."""
        payload = self._get(
            "/datasets/WINDFOR/stream",
            {
                "publishDateTimeFrom": publish_from.astimezone(timezone.utc).isoformat()
                .replace("+00:00", "Z"),
                "publishDateTimeTo": publish_to.astimezone(timezone.utc).isoformat()
                .replace("+00:00", "Z"),
            },
        )
        items = self._rows(payload, "WINDFOR")
        rows: list[ForecastRow] = []
        for item in items:
            rows.append(
                ForecastRow(
                    publish_time=parse_utc(_require(item, "publishTime"), "publishTime"),
                    start_time=parse_utc(_require(item, "startTime"), "startTime"),
                    generation_mw=_generation(item),
                )
            )
        return rows

    # -- market-index prices (£/MWh) ----------------------------------------
    def fetch_prices(self, start: date, end: date) -> list[PriceRow]:
        """Day-ahead mid prices for settlement dates in the inclusive range.

        The endpoint accepts at most 7 days per request, so the range is
        chunked; chunk boundaries overlap by a few minutes and are deduped by
        (settlementDate, settlementPeriod). Rows outside the range (the
        boundary day's first interval) are dropped.
        """
        rows: dict[tuple[date, int], PriceRow] = {}
        # `To` is inclusive at 00:00, so the final day needs To = end + 1 day.
        last_to = end + timedelta(days=1)
        cursor = start
        while cursor <= end:
            chunk_to = min(cursor + timedelta(days=PRICE_MAX_RANGE_DAYS), last_to)
            payload = self._get(
                "/balancing/pricing/market-index",
                {
                    "From": cursor.isoformat(),
                    "To": chunk_to.isoformat(),
                    "dataProviders": PRICE_PROVIDER,
                },
            )
            for item in self._market_index_rows(payload):
                provider = item.get("dataProvider")
                if provider is not None and provider != PRICE_PROVIDER:
                    continue  # server-side filter, re-checked here
                settlement_date = _require(item, "settlementDate")
                period = _require(item, "settlementPeriod")
                if not isinstance(settlement_date, str):
                    raise ElexonSchemaError(
                        f"settlementDate is not a string: {settlement_date!r}"
                    )
                if isinstance(period, bool) or not isinstance(period, int):
                    raise ElexonSchemaError(
                        f"settlementPeriod is not an integer: {period!r}"
                    )
                raw_price = item.get("price")
                if isinstance(raw_price, bool) or not isinstance(raw_price, (int, float)):
                    continue  # null price -> interval simply stays unpriced
                day = date.fromisoformat(settlement_date)
                if not (start <= day <= end):
                    continue
                key = (day, period)
                row = PriceRow(
                    settlement_date=day,
                    settlement_period=period,
                    start_time=parse_utc(_require(item, "startTime"), "startTime"),
                    price_gbp_per_mwh=float(raw_price),
                )
                # overlapping chunks re-send boundary rows; keep the first
                rows.setdefault(key, row)
            cursor = chunk_to
        return sorted(rows.values(), key=lambda r: (r.settlement_date, r.settlement_period))

    # -- validation --------------------------------------------------------
    @staticmethod
    def _market_index_rows(payload: object) -> list[dict]:
        """market-index wraps rows in {"metadata": ..., "data": [...]}; accept a bare list too."""
        items = payload
        if isinstance(payload, dict):
            items = payload.get("data")
        if not isinstance(items, list):
            raise ElexonSchemaError(
                f"market-index response is not a JSON array of rows: {type(payload)}"
            )
        rows = []
        for item in items:
            if not isinstance(item, dict):
                raise ElexonSchemaError(
                    f"market-index response contains a non-object row: {item!r}"
                )
            rows.append(item)
        return rows

    @staticmethod
    def _rows(payload: object, dataset: str) -> list[dict]:
        if not isinstance(payload, list):
            raise ElexonSchemaError(f"{dataset} response is not a JSON array: {type(payload)}")
        rows = []
        for item in payload:
            if not isinstance(item, dict):
                raise ElexonSchemaError(f"{dataset} response contains a non-object row: {item!r}")
            ds = item.get("dataset")
            if ds is not None and ds != dataset:
                raise ElexonSchemaError(f"expected dataset {dataset}, got {ds!r}")
            rows.append(item)
        return rows
