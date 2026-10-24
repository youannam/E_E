"""Role-specific business endpoints layered beside the original security APIs."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Account, Device, FinanceRecord, MonitoredUser, WorkspaceItem, utc_now
from backend.rbac import require_permission

router = APIRouter(tags=["Business workspaces"])

class DeviceCreate(BaseModel):
    device_id: str = Field(min_length=2, max_length=80)
    device_type: str = Field(min_length=2, max_length=30)
    user_id: int | None = None

class DeviceUpdate(BaseModel):
    status: str = Field(min_length=2, max_length=20)

class WorkItemCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)

class FinanceRecordCreate(BaseModel):
    record_type: str = Field(pattern="^(INVOICE|EXPENSE|BUDGET)$")
    reference: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=1000)
    amount: float = Field(ge=0, le=1000000000000)
    currency: str = Field(default="EGP", pattern="^[A-Z]{3}$")

class FinanceRecordStatus(BaseModel):
    status: str = Field(pattern="^(PENDING|APPROVED|REJECTED|PAID)$")


def item_out(item: WorkspaceItem):
    return {"id": item.id, "title": item.title, "description": item.description, "status": item.status,
            "category": item.category, "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None}

@router.get("/it/devices")
def list_devices(_: Account = Depends(require_permission("devices.view")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Device).order_by(Device.last_seen.desc(), Device.device_id)).all()
    return [{"id": d.id, "device_id": d.device_id, "user_id": d.user_id, "device_type": d.device_type,
             "status": d.status, "first_seen": d.first_seen.isoformat() if d.first_seen else None,
             "last_seen": d.last_seen.isoformat() if d.last_seen else None} for d in rows]

@router.get("/it/support-tickets")
def list_support_tickets(account: Account = Depends(require_permission("devices.view")), db: Session = Depends(get_db)):
    stmt = select(WorkspaceItem).where(WorkspaceItem.category == "SUPPORT").order_by(WorkspaceItem.updated_at.desc())
    if account.role != "ADMIN": stmt = stmt.where(WorkspaceItem.owner_account_id == account.id)
    return [item_out(i) for i in db.scalars(stmt).all()]

@router.post("/it/support-tickets", status_code=201)
def create_support_ticket(body: WorkItemCreate, account: Account = Depends(require_permission("devices.manage")), db: Session = Depends(get_db)):
    row = WorkspaceItem(owner_account_id=account.id, title=body.title.strip(), description=body.description.strip(), category="SUPPORT", status="OPEN")
    db.add(row); db.commit(); db.refresh(row); return item_out(row)

@router.post("/it/devices", status_code=201)
def create_device(body: DeviceCreate, _: Account = Depends(require_permission("devices.manage")), db: Session = Depends(get_db)):
    existing = db.scalar(select(Device).where(Device.device_id == body.device_id.strip()))
    if existing:
        raise HTTPException(status_code=409, detail="A device with this ID already exists")
    row = Device(device_id=body.device_id.strip(), device_type=body.device_type.strip().upper(), user_id=body.user_id, status="ACTIVE")
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "device_id": row.device_id, "user_id": row.user_id, "device_type": row.device_type, "status": row.status}

@router.patch("/it/devices/{device_id}")
def update_device(device_id: int, body: DeviceUpdate, _: Account = Depends(require_permission("devices.manage")), db: Session = Depends(get_db)):
    row = db.get(Device, device_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Device not found")
    row.status = body.status.strip().upper(); row.last_seen = utc_now()
    db.commit(); db.refresh(row)
    return {"id": row.id, "device_id": row.device_id, "user_id": row.user_id, "device_type": row.device_type, "status": row.status}

@router.get("/engineering/projects")
def list_projects(account: Account = Depends(require_permission("projects.view")), db: Session = Depends(get_db)):
    stmt = select(WorkspaceItem).where(WorkspaceItem.category == "PROJECT").order_by(WorkspaceItem.updated_at.desc())
    if account.role != "ADMIN": stmt = stmt.where(WorkspaceItem.owner_account_id == account.id)
    return [item_out(i) for i in db.scalars(stmt).all()]

@router.post("/engineering/projects", status_code=201)
def create_project(body: WorkItemCreate, account: Account = Depends(require_permission("projects.manage")), db: Session = Depends(get_db)):
    row = WorkspaceItem(owner_account_id=account.id, title=body.title.strip(), description=body.description.strip(), category="PROJECT", status="OPEN")
    db.add(row); db.commit(); db.refresh(row); return item_out(row)

@router.get("/hr/requests")
def list_hr_requests(account: Account = Depends(require_permission("hr.records.view")), db: Session = Depends(get_db)):
    stmt = select(WorkspaceItem).where(WorkspaceItem.category == "HR_REQUEST").order_by(WorkspaceItem.updated_at.desc())
    if account.role != "ADMIN": stmt = stmt.where(WorkspaceItem.owner_account_id == account.id)
    return [item_out(i) for i in db.scalars(stmt).all()]

@router.post("/hr/requests", status_code=201)
def create_hr_request(body: WorkItemCreate, account: Account = Depends(require_permission("hr.records.manage")), db: Session = Depends(get_db)):
    row = WorkspaceItem(owner_account_id=account.id, title=body.title.strip(), description=body.description.strip(), category="HR_REQUEST", status="OPEN")
    db.add(row); db.commit(); db.refresh(row); return item_out(row)

@router.get("/finance/requests")
def list_finance_requests(account: Account = Depends(require_permission("finance.records.view")), db: Session = Depends(get_db)):
    stmt = select(WorkspaceItem).where(WorkspaceItem.category == "FINANCE_REQUEST").order_by(WorkspaceItem.updated_at.desc())
    if account.role != "ADMIN": stmt = stmt.where(WorkspaceItem.owner_account_id == account.id)
    return [item_out(i) for i in db.scalars(stmt).all()]

@router.post("/finance/requests", status_code=201)
def create_finance_request(body: WorkItemCreate, account: Account = Depends(require_permission("finance.records.manage")), db: Session = Depends(get_db)):
    row = WorkspaceItem(owner_account_id=account.id, title=body.title.strip(), description=body.description.strip(), category="FINANCE_REQUEST", status="OPEN")
    db.add(row); db.commit(); db.refresh(row); return item_out(row)

@router.get("/employee/profile")
def own_employee_profile(account: Account = Depends(require_permission("employee.profile.view"))):
    # Deliberately returns only the signed-in account's basic profile; never other employees' data.
    return {"id": account.id, "username": account.username, "email": account.email,
            "job_role": account.job_role, "is_active": account.is_active, "created_at": account.created_at.isoformat() if account.created_at else None}


@router.get("/hr/employees")
def list_hr_employees(_: Account = Depends(require_permission("hr.records.view")), db: Session = Depends(get_db)):
    # HR-only directory: no activity, alert, password or security evidence fields are returned.
    rows = db.scalars(select(Account).where(Account.role != "ADMIN").order_by(Account.username)).all()
    return [{"id": a.id, "username": a.username, "job_role": a.job_role, "is_active": a.is_active, "created_at": a.created_at.isoformat() if a.created_at else None} for a in rows]

@router.get("/finance/records")
def list_finance_records(_: Account = Depends(require_permission("finance.records.view")), db: Session = Depends(get_db)):
    rows = db.scalars(select(FinanceRecord).order_by(FinanceRecord.updated_at.desc(), FinanceRecord.id.desc())).all()
    return [{"id": r.id, "record_type": r.record_type, "reference": r.reference, "description": r.description, "amount": r.amount, "currency": r.currency, "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]

@router.post("/finance/records", status_code=201)
def create_finance_record(body: FinanceRecordCreate, account: Account = Depends(require_permission("finance.records.manage")), db: Session = Depends(get_db)):
    if db.scalar(select(FinanceRecord.id).where(FinanceRecord.reference == body.reference.strip())) is not None:
        raise HTTPException(status_code=409, detail="A finance record with this reference already exists")
    row = FinanceRecord(owner_account_id=account.id, record_type=body.record_type, reference=body.reference.strip(), description=body.description.strip(), amount=body.amount, currency=body.currency, status="PENDING")
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "record_type": row.record_type, "reference": row.reference, "description": row.description, "amount": row.amount, "currency": row.currency, "status": row.status}

@router.patch("/finance/records/{record_id}")
def update_finance_record(record_id: int, body: FinanceRecordStatus, _: Account = Depends(require_permission("finance.records.manage")), db: Session = Depends(get_db)):
    row = db.get(FinanceRecord, record_id)
    if row is None: raise HTTPException(status_code=404, detail="Finance record not found")
    row.status = body.status; row.updated_at = utc_now(); db.commit(); db.refresh(row)
    return {"id": row.id, "record_type": row.record_type, "reference": row.reference, "description": row.description, "amount": row.amount, "currency": row.currency, "status": row.status}
