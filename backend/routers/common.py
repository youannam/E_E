"""Small helpers shared by several routers."""

from fastapi import HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

MAX_PAGE_SIZE = 100


class Pagination:
    """FastAPI dependency for ?page=1&page_size=20 (page_size is capped to protect the server)."""

    def __init__(self, page: int = Query(1, ge=1, le=100_000),
                 page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE)):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def paginate(db: Session, query, pagination: Pagination) -> tuple[list, int]:
    """Run a SELECT with LIMIT/OFFSET and also return the total number of matching rows."""
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = list(db.scalars(query.offset(pagination.offset).limit(pagination.page_size)))
    return rows, total


def get_or_404(db: Session, model, object_id: int, name: str):
    obj = db.get(model, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{name} {object_id} not found")
    return obj
