import { useState, type FormEvent } from "react";

import { api } from "../api/client";

import type { Page, UserSummary } from "../api/types";
import { RISK_LEVELS } from "../api/types";
import { useApi } from "../api/useApi";
import { RiskBadge, SimulatedTag } from "../components/Badges";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataState } from "../components/DataState";
import { PageHeader } from "../components/Layout";
import { useAuth } from "../auth/AuthContext";
import { Pagination } from "../components/Pagination";
import { buildQuery, formatDateTime, humanize } from "../utils/format";

const PAGE_SIZE = 25;
const DEPARTMENTS = ["Engineering", "Finance", "Human Resources", "IT", "Sales"];

export function UsersPage() {
  const { account } = useAuth();
  const isAdmin = account?.role === "ADMIN";
  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newDepartment, setNewDepartment] = useState("Engineering");
  const [newJobRole, setNewJobRole] = useState("Software Engineer");
  const [jobPermissions, setJobPermissions] = useState<string[]>(["read_project_files", "write_project_files", "use_development_tools"]);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState({ username: "", email: "", department: "", job_role: "", status: "ACTIVE" });
  const [pendingDelete, setPendingDelete] = useState<UserSummary | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const [sort, setSort] = useState("risk");
  const [page, setPage] = useState(1);
  const query = buildQuery({ search: search.trim(), department, risk_level: riskLevel, sort, page, page_size: PAGE_SIZE });
  const users = useApi<Page<UserSummary>>(`/users${query}`);

  async function createUser(event: FormEvent) {
    event.preventDefault(); setBusy(true); setActionError(null); setActionMessage(null);
    try {
      await api.post<UserSummary>("/users", { username: newUsername.trim().toLowerCase(), email: newEmail.trim() || null, department: newDepartment, job_role: newJobRole, job_permissions: jobPermissions, is_synthetic: true });
      setNewUsername(""); setNewEmail(""); setActionMessage("Monitored user added."); users.reload();
    } catch (err) { setActionError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function saveUser() {
    if (editing === null) return; setBusy(true); setActionError(null); setActionMessage(null);
    try {
      await api.patch<UserSummary>(`/users/${editing}`, { ...draft, email: draft.email.trim() || null });
      setEditing(null); setActionMessage("Monitored user updated."); users.reload();
    } catch (err) { setActionError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function deleteUser() {
    if (!pendingDelete) return; setBusy(true); setActionError(null); setActionMessage(null);
    try {
      await api.delete<void>(`/users/${pendingDelete.id}`);
      setActionMessage(`Deleted ${pendingDelete.username} and its associated activity/alert history.`); setPendingDelete(null); users.reload();
    } catch (err) { setActionError((err as Error).message); setPendingDelete(null); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Monitored users" subtitle="Manage monitored employees and review their risk posture." />
      {isAdmin && <section className="panel"><h2>Add monitored user</h2><form className="filters account-create" onSubmit={createUser}>
        <label>Username<input required minLength={3} pattern="[a-z0-9._-]+" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} /></label>
        <label>Email (optional)<input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} /></label>
        <label>Department<input required minLength={2} value={newDepartment} onChange={(e) => setNewDepartment(e.target.value)} /></label>
        <label>Job role<select value={newJobRole} onChange={(e) => { const v=e.target.value; setNewJobRole(v); const presets: Record<string,string[]>={"Software Engineer":["read_project_files","write_project_files","use_development_tools"],"IT Support":["manage_workstations","review_device_events","support_accounts"],"System Administrator":["manage_workstations","review_device_events","support_accounts","manage_access_requests"],"Security Analyst":["review_security_alerts","investigate_events","preserve_evidence","escalate_incidents"],"HR Specialist":["read_hr_records","manage_hr_records"],"Finance Specialist":["read_financial_records","manage_financial_records"],"Employee":["access_assigned_business_apps"]}; setJobPermissions(presets[v] || ["access_assigned_business_apps"]); }}><option>Software Engineer</option><option>IT Support</option><option>System Administrator</option><option>Security Analyst</option><option>HR Specialist</option><option>Finance Specialist</option><option>Employee</option></select></label>
        <fieldset className="permission-picker"><legend>Job-role permissions</legend>{jobPermissions.map((permission)=><label key={permission}><input type="checkbox" checked onChange={()=>setJobPermissions(jobPermissions.filter(p=>p!==permission))}/>{humanize(permission)}</label>)}<p className="muted small">These describe the monitored employee's allowed business capabilities. They are not Eagle Eye login credentials.</p></fieldset>
        <button className="button" disabled={busy}>Add user</button>
      </form></section>}
      {actionMessage && <p className="form-success" role="status">{actionMessage}</p>}
      {actionError && <p className="form-error" role="alert">{actionError}</p>}
      <form className="filters" onSubmit={(e) => e.preventDefault()} aria-label="User filters">
        <label>
          Search
          <input type="search" placeholder="Username" value={search}
                 onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        </label>
        <label>
          Department
          <select value={department} onChange={(e) => { setDepartment(e.target.value); setPage(1); }}>
            <option value="">All departments</option>
            {DEPARTMENTS.map((name) => <option key={name}>{name}</option>)}
          </select>
        </label>
        <label>
          Current risk
          <select value={riskLevel} onChange={(e) => { setRiskLevel(e.target.value); setPage(1); }}>
            <option value="">Any level</option>
            {RISK_LEVELS.map((level) => <option key={level} value={level}>{humanize(level)}</option>)}
          </select>
        </label>
        <label>
          Sort by
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="risk">Highest risk first</option>
            <option value="username">Username</option>
            <option value="last_activity">Most recently active</option>
          </select>
        </label>
      </form>

      <section className="panel">
        <DataState loading={users.loading && !users.data} error={users.error} onRetry={users.reload}
                   empty={users.data?.total === 0} emptyMessage="No users match these filters.">
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Department</th>
                <th>Job role</th>
                <th>Current risk</th>
                <th>Alerts</th>
                <th>Last activity</th>
                {isAdmin && <th>Admin actions</th>}
              </tr>
            </thead>
            <tbody>
              {users.data?.items.map((user) => {
                const isEditing = editing === user.id;
                return <tr key={user.id}>
                  <td>{isEditing ? <input aria-label="Username" value={draft.username} onChange={(e) => setDraft({ ...draft, username: e.target.value })} /> : <><a href={`#/users/${user.id}`}>{user.username}</a> {user.is_synthetic && <SimulatedTag />}</>}</td>
                  <td>{isEditing ? <input aria-label="Department" value={draft.department} onChange={(e) => setDraft({ ...draft, department: e.target.value })} /> : user.department}</td>
                  <td>{isEditing ? <input aria-label="Job role" value={draft.job_role} onChange={(e) => setDraft({ ...draft, job_role: e.target.value })} /> : user.job_role}</td>
                  <td><RiskBadge level={user.current_risk_level} score={user.current_risk_score} /></td>
                  <td>{user.alert_count} {user.open_alert_count > 0 && <span className="muted">({user.open_alert_count} open)</span>}</td>
                  <td>{formatDateTime(user.last_activity_at)}</td>
                  {isAdmin && <td><div className="action-buttons">{isEditing ? <><button className="button" disabled={busy} onClick={saveUser}>Save</button><button className="button button-secondary" onClick={() => setEditing(null)}>Cancel</button></> : <><button className="button button-secondary" onClick={() => { setEditing(user.id); setDraft({ username: user.username, email: user.email ?? "", department: user.department, job_role: user.job_role, status: user.status }); }}>Edit</button><button className="button button-secondary" onClick={() => setPendingDelete(user)}>Delete</button></>}</div></td>}
                </tr>;
              })}
            </tbody>
          </table>
          {users.data && <Pagination page={page} pageSize={PAGE_SIZE} total={users.data.total} onPageChange={setPage} />}
        </DataState>
      </section>
      {pendingDelete && <ConfirmDialog title="Delete monitored user" message={`Delete ${pendingDelete.username} and permanently remove its associated simulated activities, analysis results, and alerts? This cannot be undone.`} confirmLabel="Delete user and history" busy={busy} onCancel={() => setPendingDelete(null)} onConfirm={deleteUser} />}
    </>
  );
}
