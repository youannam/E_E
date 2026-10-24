import { useEffect, useState, type FormEvent } from "react";

import { api } from "../api/client";
import type { Account, Role } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataState } from "../components/DataState";
import { PageHeader } from "../components/Layout";
import { formatDateTime } from "../utils/format";

const JOB_ROLE_PERMISSIONS: Record<string, string[]> = {
  "Security Analyst": ["alerts.view", "alerts.investigate", "alerts.resolve", "actions.escalate", "workspace.view", "workspace.create", "workspace.update"],
  "IT Support": ["workspace.view", "workspace.create", "workspace.update", "devices.view", "devices.manage"],
  "System Administrator": ["workspace.view", "workspace.create", "workspace.update", "devices.view", "devices.manage"],
  "Software Engineer": ["workspace.view", "workspace.create", "workspace.update", "projects.view", "projects.manage"],
  "HR Specialist": ["workspace.view", "workspace.create", "workspace.update", "hr.records.view", "hr.records.manage", "employee.profile.view"],
  "Finance Specialist": ["workspace.view", "workspace.create", "workspace.update", "finance.records.view", "finance.records.manage"],
  Employee: ["workspace.view", "workspace.create", "workspace.update", "employee.profile.view"],
};
const PERMISSION_OPTIONS: [string, string][] = [
  ["alerts.view", "View alerts"], ["alerts.investigate", "Investigate / add notes / assign cases"], ["alerts.resolve", "Resolve alerts / mark false positives"], ["users.view", "View monitored users"], ["users.manage", "Add or edit monitored users"], ["activities.view", "View activity evidence"], ["rules.manage", "Manage detection rules"], ["actions.escalate", "Escalate incidents"], ["accounts.manage", "Manage accounts"], ["workspace.view", "View own workspace"], ["workspace.create", "Create workspace items"], ["workspace.update", "Update workspace items"], ["devices.view", "View IT devices"], ["devices.manage", "Manage IT devices"], ["projects.view", "View projects/builds"], ["projects.manage", "Manage projects/builds"], ["hr.records.view", "View HR records"], ["hr.records.manage", "Manage HR records"], ["finance.records.view", "View finance records"], ["finance.records.manage", "Manage finance records"], ["employee.profile.view", "View own employee profile"],
];

export function AccountsPage() {
  const { account: current } = useAuth();
  const accounts = useApi<Account[]>("/accounts");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("ANALYST");
  const [jobRole, setJobRole] = useState("Security Analyst");
  const [permissions, setPermissions] = useState<string[]>(JOB_ROLE_PERMISSIONS["Security Analyst"]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, { role: Role; is_active: boolean; permissions: string[] }>>({});
  const [pendingDelete, setPendingDelete] = useState<Account | null>(null);
  const [resetRequests, setResetRequests] = useState<Array<{id:number; username:string; email:string|null; status:string; created_at:string}>>([]);
  const [resetPasswords, setResetPasswords] = useState<Record<number,string>>({});
  async function loadResetRequests() { try { setResetRequests(await api.get<typeof resetRequests>("/password-reset-requests")); } catch { /* admin-only endpoint; surfaced below on reload */ } }
  useEffect(() => { void loadResetRequests(); const timer = window.setInterval(() => void loadResetRequests(), 15000); return () => window.clearInterval(timer); }, []);
  async function reviewReset(id:number, action:"approve"|"reject") {
    setError(null); setMessage(null); setBusy(true);
    try {
      await api.post(`/password-reset-requests/${id}/review`, {action, ...(action === "approve" ? {new_password: resetPasswords[id] ?? ""} : {})});
      setMessage(action === "approve" ? "Password reset approved. The temporary password was emailed to the registered user; they must set a new password before signing in." : "Reset request rejected.");
      setResetPasswords(old => {const next={...old}; delete next[id]; return next;});
      await loadResetRequests();
    } catch(err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function create(event: FormEvent) {
    event.preventDefault(); setError(null); setMessage(null); setBusy(true);
    try {
      await api.post<Account>("/accounts", { username: username.trim(), email: email.trim() || null, password, role, job_role: jobRole, permissions: role === "ADMIN" ? [] : permissions, is_active: true });
      setUsername(""); setEmail(""); setPassword(""); setRole("ANALYST"); setJobRole("Security Analyst"); setPermissions(JOB_ROLE_PERMISSIONS["Security Analyst"]);
      setMessage("Account created successfully."); accounts.reload();
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function save(account: Account) {
    const draft = drafts[account.id] ?? { role: account.role, is_active: account.is_active, permissions: account.permissions ?? [] };
    setError(null); setMessage(null); setBusy(true);
    try {
      await api.patch<Account>(`/accounts/${account.id}`, { ...draft, permissions: draft.role === "ADMIN" ? [] : draft.permissions });
      setMessage(`Updated ${account.username}.`);
      setDrafts((old) => { const next = { ...old }; delete next[account.id]; return next; });
      accounts.reload();
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!pendingDelete) return;
    setError(null); setBusy(true);
    try {
      await api.delete<void>(`/accounts/${pendingDelete.id}`);
      setMessage(`Deleted account ${pendingDelete.username}.`); setPendingDelete(null); accounts.reload();
    } catch (err) { setError((err as Error).message); setPendingDelete(null); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader title="Account & access management" subtitle="Administrator-only control of login accounts, roles, and account status." />
    <p className="form-notice">Role changes are enforced by the backend. At least one active administrator must remain, and you cannot delete or deactivate your own signed-in account.</p>
    {message && <p className="form-success" role="status">{message}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <section className="panel">
      <h2>Password reset requests {resetRequests.filter(r => r.status === "PENDING").length > 0 && `(${resetRequests.filter(r => r.status === "PENDING").length} pending)`}</h2>
      <p className="muted">Requests are refreshed automatically. Only an administrator can approve a reset and set a temporary password.</p>
      {resetRequests.length === 0 ? <p className="muted">No reset requests yet.</p> : <table className="table"><thead><tr><th>Requested account</th><th>Submitted</th><th>Status</th><th>Administrator action</th></tr></thead><tbody>{resetRequests.map(r => <tr key={r.id}><td><strong>{r.username}</strong><div className="muted small">{r.email ?? "No email supplied"}</div></td><td>{formatDateTime(r.created_at)}</td><td>{r.status}</td><td>{r.status === "PENDING" ? <div className="action-buttons"><input aria-label={`Temporary password for ${r.username}`} type="password" minLength={10} placeholder="Temporary password (10+ chars)" value={resetPasswords[r.id] ?? ""} onChange={e => setResetPasswords(old => ({...old,[r.id]:e.target.value}))}/><button className="button" disabled={busy || (resetPasswords[r.id] ?? "").length < 10} onClick={() => void reviewReset(r.id,"approve")}>Approve & reset</button><button className="button button-secondary" disabled={busy} onClick={() => void reviewReset(r.id,"reject")}>Reject</button></div> : "Reviewed"}</td></tr>)}</tbody></table>}
    </section>
    <section className="panel">
      <h2>Create account</h2>
      <form className="filters account-create" onSubmit={create}>
        <label>Username<input required minLength={3} maxLength={50} value={username} onChange={(e) => setUsername(e.target.value)} pattern="[A-Za-z0-9._-]+" /></label>
        <label>Email (optional)<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label>Temporary password<input required minLength={10} type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        <label>Job Role<select value={jobRole} onChange={(e) => { const next = e.target.value; setJobRole(next); setPermissions(JOB_ROLE_PERMISSIONS[next] ?? JOB_ROLE_PERMISSIONS.Employee); }}><option>Security Analyst</option><option>IT Support</option><option>Software Engineer</option><option>System Administrator</option><option>HR Specialist</option><option>Finance Specialist</option><option>Employee</option></select></label>
        <label>Application access<select value={role} onChange={(e) => setRole(e.target.value as Role)}><option value="ANALYST">Custom access / Analyst</option><option value="ADMIN">Admin — full access</option></select></label>
        {role === "ANALYST" && <fieldset className="permission-picker"><legend>Permissions for this account</legend>{PERMISSION_OPTIONS.map(([key, label]) => <label key={key}><input type="checkbox" checked={permissions.includes(key)} onChange={(e) => setPermissions(old => e.target.checked ? [...old, key] : old.filter(x => x !== key))} /> {label}</label>)}</fieldset>}
        <button className="button" disabled={busy} type="submit">Create account</button>
      </form>
    </section>
    <section className="panel">
      <h2>Existing accounts</h2>
      <DataState loading={accounts.loading && !accounts.data} error={accounts.error} onRetry={accounts.reload} empty={accounts.data?.length === 0} emptyMessage="No accounts found.">
        <table className="table">
          <thead><tr><th>Account</th><th>Job Role / App Access</th><th>Status</th><th>Last login</th><th>Actions</th></tr></thead>
          <tbody>{accounts.data?.map((item) => {
            const draft = drafts[item.id] ?? { role: item.role, is_active: item.is_active, permissions: item.permissions ?? [] };
            const self = item.id === current?.id;
            return <tr key={item.id}>
              <td><strong>{item.username}</strong><div className="muted small">{item.email ?? "No email"}</div></td>
              <td><div>{item.job_role ?? "Security Analyst"}</div><small className="muted">{draft.role}</small><select aria-label={`Role for ${item.username}`} value={draft.role} onChange={(e) => setDrafts((old) => ({ ...old, [item.id]: { ...draft, role: e.target.value as Role } }))}><option value="ADMIN">Admin</option><option value="ANALYST">Analyst</option></select>{draft.role !== "ADMIN" && <details className="account-permission-details"><summary>Configure permissions ({draft.permissions.length})</summary>{PERMISSION_OPTIONS.map(([key,label])=><label key={key} className="permission-inline"><input type="checkbox" checked={draft.permissions.includes(key)} onChange={e=>setDrafts(old=>({...old,[item.id]:{...draft,permissions:e.target.checked?[...draft.permissions,key]:draft.permissions.filter(x=>x!==key)}}))}/>{label}</label>)}</details>}</td>
              <td><select aria-label={`Status for ${item.username}`} value={draft.is_active ? "active" : "inactive"} disabled={self} onChange={(e) => setDrafts((old) => ({ ...old, [item.id]: { ...draft, is_active: e.target.value === "active" } }))}><option value="active">Active</option><option value="inactive">Disabled</option></select></td>
              <td>{formatDateTime(item.last_login)}</td>
              <td><div className="action-buttons"><button className="button" disabled={busy || (draft.role === item.role && draft.is_active === item.is_active && JSON.stringify(draft.permissions) === JSON.stringify(item.permissions ?? []))} onClick={() => save(item)}>Save</button><button className="button button-secondary" disabled={busy || self} onClick={() => setPendingDelete(item)}>Delete</button></div></td>
            </tr>;
          })}</tbody>
        </table>
      </DataState>
    </section>
    {pendingDelete && <ConfirmDialog title="Delete login account" message={`Permanently delete the ${pendingDelete.role} account “${pendingDelete.username}”? This action cannot be undone.`} confirmLabel="Delete account" busy={busy} onCancel={() => setPendingDelete(null)} onConfirm={remove} />}
  </>;
}
