"""Central permission catalogue and job-role policy profiles for Eagle Eye."""
from fastapi import Depends, HTTPException
from backend.security import get_current_account

PERMISSIONS = {
    "alerts.view": "View alerts and risk signals",
    "alerts.investigate": "Investigate alerts, add notes and assign cases",
    "alerts.resolve": "Resolve alerts or mark false positives",
    "users.view": "View monitored employee directory",
    "users.manage": "Add/edit monitored employee records",
    "activities.view": "View raw activity and evidence timelines",
    "rules.manage": "Configure detection rules",
    "accounts.manage": "Create accounts and manage access",
    "actions.escalate": "Escalate a case to the security team",
}
ROLE_DEFAULTS = {
    "ADMIN": list(PERMISSIONS),
    "ANALYST": ["alerts.view", "alerts.investigate", "alerts.resolve", "actions.escalate"],
}
JOB_ROLE_DEFAULTS = {
    "software engineer": ["read_project_files", "write_project_files", "use_development_tools"],
    "developer": ["read_project_files", "write_project_files", "use_development_tools"],
    "it": ["manage_workstations", "review_device_events", "support_accounts"],
    "it support": ["manage_workstations", "review_device_events", "support_accounts"],
    "system administrator": ["manage_workstations", "review_device_events", "support_accounts", "manage_access_requests"],
    "security analyst": ["review_security_alerts", "investigate_events", "preserve_evidence", "escalate_incidents"],
    "hr": ["read_hr_records", "manage_hr_records"],
    "human resources": ["read_hr_records", "manage_hr_records"],
    "finance": ["read_financial_records", "manage_financial_records"],
    "employee": ["access_assigned_business_apps"],
}

def normalize_account_permissions(role, permissions):
    allowed = set(PERMISSIONS)
    if permissions is None or len(permissions) == 0:
        return ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["ANALYST"]).copy()
    unknown = set(permissions) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown permissions: {', '.join(sorted(unknown))}")
    if role == "ADMIN":
        # Admins retain the full set to prevent accidental self-lockout.
        return ROLE_DEFAULTS["ADMIN"].copy()
    return sorted(set(permissions))

def default_job_permissions(job_role):
    key = (job_role or "employee").strip().lower()
    return JOB_ROLE_DEFAULTS.get(key, JOB_ROLE_DEFAULTS["employee"]).copy()

def require_permission(permission):
    def check(account=Depends(get_current_account)):
        grants = set(account.permissions or ROLE_DEFAULTS.get(account.role, []))
        if account.role == "ADMIN":
            return account
        if permission not in grants:
            raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
        return account
    return check
