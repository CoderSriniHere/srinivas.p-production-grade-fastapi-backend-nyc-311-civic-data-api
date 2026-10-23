"""
Loads NYC 311 service requests from the Socrata Open Data API into the
`complaints` table, handling the raw feed's nulls and inconsistent values:
  - incident_zip is sometimes missing, blank, or the literal string "N/A"
  - borough is sometimes "Unspecified" instead of a real borough name
  - agency/complaint_type/status are occasionally blank despite the column
    being NOT NULL on our side, so they get a sane default instead

Run with: python -m app.etl.load_complaints --rows 500000
"""
import argparse
import asyncio
import time
from datetime import datetime

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import Complaint

PAGE_SIZE = 1000
MAX_RETRIES = 3
VALID_BOROUGHS = {"MANHATTAN", "BROOKLYN", "QUEENS", "BRONX", "STATEN ISLAND"}
FIELDS = (
    "unique_key,agency,complaint_type,descriptor,status,borough,"
    "incident_zip,incident_address,created_date,closed_date,resolution_description"
)


def fetch_page(base_url: str, offset: int, limit: int) -> list[dict]:
    params = {"$select": FIELDS, "$limit": limit, "$offset": offset, "$order": "unique_key"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2 * attempt)
    return []


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _clean_zip(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value or value.upper() == "N/A":
        return None
    return value[:10]


def coerce_row(raw: dict) -> dict | None:
    """Map one raw Socrata record to Complaint columns, or None to skip an unusable row."""
    unique_key = raw.get("unique_key")
    created_date = _parse_datetime(raw.get("created_date"))
    if not unique_key or created_date is None:
        return None  # both are NOT NULL columns -- nothing sensible to insert

    borough = (raw.get("borough") or "").strip().upper()
    if borough not in VALID_BOROUGHS:
        borough = "UNKNOWN"

    return {
        "unique_key": unique_key,
        "agency": (raw.get("agency") or "UNKNOWN").strip().upper()[:10],
        "complaint_type": (raw.get("complaint_type") or "Unspecified").strip()[:255],
        "descriptor": raw.get("descriptor"),
        "status": (raw.get("status") or "Open").strip()[:50],
        "borough": borough,
        "incident_zip": _clean_zip(raw.get("incident_zip")),
        "incident_address": raw.get("incident_address"),
        "created_date": created_date,
        "closed_date": _parse_datetime(raw.get("closed_date")),
        "resolution_description": raw.get("resolution_description"),
    }


async def load(total_rows: int) -> None:
    settings = get_settings()
    inserted = 0
    skipped = 0
    offset = 0

    async with AsyncSessionLocal() as db:
        while inserted + skipped < total_rows:
            batch_limit = min(PAGE_SIZE, total_rows - inserted - skipped)
            raw_rows = fetch_page(settings.socrata_api_url, offset, batch_limit)
            if not raw_rows:
                break  # exhausted the dataset before hitting total_rows
            offset += len(raw_rows)

            rows = [row for r in raw_rows if (row := coerce_row(r)) is not None]
            skipped += len(raw_rows) - len(rows)

            if rows:
                stmt = pg_insert(Complaint).values(rows).on_conflict_do_nothing(index_elements=["unique_key"])
                await db.execute(stmt)
                await db.commit()
                inserted += len(rows)

            print(f"loaded {inserted} rows, skipped {skipped} invalid rows (offset {offset})")

    print(f"done: {inserted} inserted, {skipped} skipped")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load NYC 311 complaints from Socrata into Postgres")
    parser.add_argument("--rows", type=int, default=500_000, help="number of rows to pull")
    args = parser.parse_args()
    asyncio.run(load(args.rows))


if __name__ == "__main__":
    main()
