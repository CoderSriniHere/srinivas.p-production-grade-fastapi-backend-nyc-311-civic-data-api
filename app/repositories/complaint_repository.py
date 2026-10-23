from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Complaint


class ComplaintRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _filtered(
        self,
        agency_code: str,
        borough: str | None = None,
        complaint_type: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        query = select(Complaint).where(Complaint.agency == agency_code)
        if borough:
            query = query.where(Complaint.borough == borough)
        if complaint_type:
            query = query.where(Complaint.complaint_type == complaint_type)
        if status:
            query = query.where(Complaint.status == status)
        if start_date:
            query = query.where(Complaint.created_date >= start_date)
        if end_date:
            query = query.where(Complaint.created_date <= end_date)
        return query

    async def list_by_agency(self, agency_code: str, limit: int = 100, offset: int = 0) -> list[Complaint]:
        result = await self.db.execute(
            select(Complaint)
            .where(Complaint.agency == agency_code)
            .order_by(Complaint.created_date.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_paginated(
        self,
        agency_code: str,
        borough: str | None = None,
        complaint_type: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[Complaint], int]:
        base_query = self._filtered(agency_code, borough, complaint_type, status, start_date, end_date)

        count_result = await self.db.execute(select(func.count()).select_from(base_query.subquery()))
        total = count_result.scalar_one()

        result = await self.db.execute(
            base_query.order_by(Complaint.created_date.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_by_id(self, complaint_id: UUID, agency_code: str) -> Complaint | None:
        result = await self.db.execute(
            select(Complaint).where(Complaint.id == complaint_id, Complaint.agency == agency_code)
        )
        return result.scalar_one_or_none()

    async def update_status(self, complaint_id: UUID, agency_code: str, status: str) -> Complaint | None:
        complaint = await self.get_by_id(complaint_id, agency_code)
        if complaint is None:
            return None
        complaint.status = status
        await self.db.commit()
        await self.db.refresh(complaint)
        return complaint

    async def create(self, agency_code: str, **fields) -> Complaint:
        complaint = Complaint(agency=agency_code, **fields)
        self.db.add(complaint)
        await self.db.commit()
        await self.db.refresh(complaint)
        return complaint


def get_repo(db: AsyncSession = Depends(get_db)) -> ComplaintRepository:
    return ComplaintRepository(db)