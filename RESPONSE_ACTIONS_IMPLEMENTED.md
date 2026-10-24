# Eagle Eye – Alert response actions

## Implemented in this project build
- Alert response playbook now includes admin-only (via `users.manage`) actions for the existing synthetic monitored employee attached to the alert: suspend, reactivate, and restrict job permissions.
- Suspend/reactivate persist `MonitoredUser.status` as `INACTIVE`/`ACTIVE`.
- Restrict clears the monitored employee's configured `job_permissions`; an administrator can restore the permissions from the existing user management page.
- Each action is written to alert history and to the audit log, then committed to the database.
- The web and Flutter clients consume the same backend-provided action list; Flutter reports the specific completed action.

## Important scope note
These 25 entries are synthetic monitored employee records, not external login identities. The suspend action changes the employee's project-side monitored status; it does not revoke an external account or disable a separate application login. The restriction action updates the employee's job-permission profile and does not block ingestion of historical activity.

## Verification
- Python backend source compiles with `python -m compileall`.
- Full pytest run did not finish within the available 20-second verification window.
- Frontend production build was not run because `frontend/node_modules` is not present in this environment; install dependencies and run `npm install && npm run build` to verify it locally.
- Flutter build was not run in this environment.
