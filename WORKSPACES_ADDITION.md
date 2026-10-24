# Eagle Eye business workspaces (additive change)

This addition preserves the existing security analyst/admin screens and adds a job-role-aware workspace to both Web and Flutter.

## Included
- Web route: `#/workspace` with a workspace label based on the signed-in account's `job_role`.
- Flutter: `My Workspace` navigation entry for both analyst and administrator navigation sets.
- API: `GET /api/v1/workspace`, `POST /api/v1/workspace`, and `PATCH /api/v1/workspace/{item_id}`.
- New `workspace_items` table, created with `checkfirst=True` during API startup so existing tables are not dropped or replaced.
- Items are private to the creating account; only an `ADMIN` account can list or update items belonging to other accounts.
- Workspace categories are tailored in the clients for IT support, software engineering, HR, finance, security analyst, and employee job roles.

## Important boundaries
This is the first additive implementation of job workspaces, not a claim that dedicated HR records, financial ledgers, IT device inventory, software build pipelines, or employee leave/hiring workflows already exist. Those domain modules still need their own data models and endpoints before they can be considered implemented. The existing security alert, activity, detection, account and rule modules were not intentionally removed or replaced.

## API behavior
- Item title: 2–160 characters.
- Description: up to 4,000 characters.
- Status values: `OPEN`, `IN_PROGRESS`, `DONE`, `CANCELLED`.
- Category values: `TASK`, `SUPPORT`, `PROJECT`, `HR_REQUEST`, `FINANCE_REQUEST`, `PERSONAL`.
- Authentication is required for every endpoint.

## Role-specific endpoints added
- `GET/POST /api/v1/it/devices`, `PATCH /api/v1/it/devices/{device_id}`: device inventory and status management, guarded by `devices.view` / `devices.manage`.
- `GET/POST /api/v1/it/support-tickets`: support tickets stored as workspace items and guarded by IT permissions.
- `GET/POST /api/v1/engineering/projects`: project task records guarded by `projects.view` / `projects.manage`.
- `GET/POST /api/v1/hr/requests`: HR request tracking guarded by HR permissions.
- `GET/POST /api/v1/finance/requests`: finance request tracking guarded by finance permissions.
- `GET /api/v1/employee/profile`: returns only the current account's basic profile.

The web and Flutter workspace screens consume the role-specific APIs available to the current job role. HR requests and finance requests are workflow/task records, not a substitute for a complete HRIS or accounting ledger; those records and approval rules must be implemented separately before production use.
- `GET /api/v1/hr/employees`: HR-only, limited directory fields (no alerts, activity, credentials or evidence).
- `GET/POST /api/v1/finance/records`, `PATCH /api/v1/finance/records/{record_id}`: finance-only invoice/expense/budget workflow records with pending/approved/rejected/paid statuses.
