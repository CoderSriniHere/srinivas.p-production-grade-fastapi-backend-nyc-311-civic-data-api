"""
Seeds one platform_users login per major NYC agency, so each agency can be
exercised end-to-end (login -> agency-scoped /complaints -> etc.) without
registering accounts by hand.

Agencies are the top 10 by real complaint volume in the NYC 311 dataset
(confirmed via a Socrata $group query) rather than a guessed list -- e.g.
FDNY, sometimes cited as a typical 311 agency, actually has zero complaints
in this dataset, so it's swapped for DHS/TLC/DPR/DOB/DOHMH which do.

Run with: python -m app.etl.seed_users
"""
import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models import PlatformUser

DEMO_PASSWORD = "srinivas"

# (agency_code, full_name, role) -- one admin and two analysts so the
# API-key, report-export, and SSE-progress flows all have a login to use.
AGENCIES = [
    ("NYPD", "NYPD Platform Account", "admin"),
    ("HPD", "HPD Platform Account", "staff"),
    ("DSNY", "DSNY Platform Account", "staff"),
    ("DOT", "DOT Platform Account", "analyst"),
    ("DEP", "DEP Platform Account", "staff"),
    ("DPR", "DPR Platform Account", "staff"),
    ("DOB", "DOB Platform Account", "analyst"),
    ("DOHMH", "DOHMH Platform Account", "staff"),
    ("DHS", "DHS Platform Account", "staff"),
    ("TLC", "TLC Platform Account", "staff"),
]


async def seed() -> None:
    hashed = hash_password(DEMO_PASSWORD)
    rows = [
        {
            "email": f"{agency_code.lower()}@nyc311.gov",
            "hashed_password": hashed,
            "full_name": full_name,
            "agency_code": agency_code,
            "role": role,
        }
        for agency_code, full_name, role in AGENCIES
    ]

    async with AsyncSessionLocal() as db:
        stmt = pg_insert(PlatformUser).values(rows).on_conflict_do_nothing(index_elements=["email"])
        result = await db.execute(stmt)
        await db.commit()

    print(f"seeded {result.rowcount} new platform users (skipped ones that already existed)")
    print(f"shared demo password for all seeded accounts: {DEMO_PASSWORD}")
    for agency_code, _, role in AGENCIES:
        print(f"  {agency_code:<6} role={role:<8} email={agency_code.lower()}@nyc311.gov")


if __name__ == "__main__":
    asyncio.run(seed())
