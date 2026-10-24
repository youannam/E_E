"""Additive business-workspace API. Items are private to their creator except for admins."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Account, WorkspaceItem, utc_now
from backend.rbac import require_permission

router = APIRouter(prefix="/workspace", tags=["Business workspace"])

class ItemCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    category: Literal["TASK", "SUPPORT", "PROJECT", "HR_REQUEST", "FINANCE_REQUEST", "PERSONAL"] = "TASK"

class ItemUpdate(BaseModel):
    status: Literal["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"]

def serialize(item: WorkspaceItem):
    return {"id": item.id, "owner_account_id": item.owner_account_id, "title": item.title, "description": item.description, "category": item.category, "status": item.status, "created_at": item.created_at.isoformat() if item.created_at else None, "updated_at": item.updated_at.isoformat() if item.updated_at else None}

@router.get("")
def list_items(account: Account = Depends(require_permission("workspace.view")), db: Session = Depends(get_db)):
    stmt = select(WorkspaceItem).order_by(WorkspaceItem.updated_at.desc(), WorkspaceItem.id.desc())
    if account.role != "ADMIN":
        stmt = stmt.where(WorkspaceItem.owner_account_id == account.id)
    items = db.scalars(stmt).all()
    return {"items": [serialize(item) for item in items], "job_role": account.job_role, "is_admin": account.role == "ADMIN"}

@router.post("", status_code=201)
def create_item(payload: ItemCreate, account: Account = Depends(require_permission("workspace.create")), db: Session = Depends(get_db)):
    category_permission = {"SUPPORT": "devices.manage", "PROJECT": "projects.manage", "HR_REQUEST": "hr.records.manage", "FINANCE_REQUEST": "finance.records.manage"}.get(payload.category)
    if category_permission and account.role != "ADMIN" and category_permission not in set(account.permissions or []):
        raise HTTPException(status_code=403, detail=f"Permission required: {category_permission}")
    item = WorkspaceItem(owner_account_id=account.id, title=payload.title.strip(), description=payload.description.strip(), category=payload.category, status="OPEN")
    db.add(item); db.commit(); db.refresh(item)
    return serialize(item)

@router.patch("/{item_id}")
def update_item(item_id: int, payload: ItemUpdate, account: Account = Depends(require_permission("workspace.update")), db: Session = Depends(get_db)):
    item = db.get(WorkspaceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workspace item not found")
    if item.owner_account_id != account.id and account.role != "ADMIN":
        raise HTTPException(status_code=403, detail="You can only update your own workspace items")
    category_permission = {"SUPPORT": "devices.manage", "PROJECT": "projects.manage", "HR_REQUEST": "hr.records.manage", "FINANCE_REQUEST": "finance.records.manage"}.get(item.category)
    if category_permission and account.role != "ADMIN" and category_permission not in set(account.permissions or []):
        raise HTTPException(status_code=403, detail=f"Permission required: {category_permission}")
    item.status = payload.status
    item.updated_at = utc_now()
    db.commit(); db.refresh(item)
    return serialize(item)
