// Page frame: side navigation, top bar and the synthetic-data notice.
import { useEffect, useState, type ReactNode } from "react";

import { useAuth } from "../auth/AuthContext";
import type { PageName } from "../utils/router";
import { api } from "../api/client";

const ADMIN_NAV: { page: PageName; label: string }[] = [
  { page: "dashboard", label: "Overview" },
  { page: "alerts", label: "Alerts" },
  { page: "users", label: "Monitored users" },
  { page: "activities", label: "Activity log" },
  { page: "simulation", label: "Detection lab" },
  { page: "rules", label: "Detection rules" },
  { page: "accounts", label: "Accounts & access" },
  { page: "workspace", label: "My Workspace" },
];
export function Layout({ current, children }: { current: PageName; children: ReactNode }) {
  const { account, logout } = useAuth();
  const [pendingResetCount, setPendingResetCount] = useState(0);
  useEffect(() => { if (account?.role !== "ADMIN") return; let live = true; const load = async () => { try { const rows = await api.get<Array<{status:string}>>("/password-reset-requests"); if (live) setPendingResetCount(rows.filter(r => r.status === "PENDING").length); } catch { /* API may be temporarily unavailable */ } }; void load(); const timer = window.setInterval(() => void load(), 15000); return () => { live = false; window.clearInterval(timer); }; }, [account?.role]);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try { return localStorage.getItem("eagle-eye-theme") === "dark" ? "dark" : "light"; }
    catch { return "light"; }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("eagle-eye-theme", theme); } catch { /* storage may be disabled */ }
  }, [theme]);
  const grants = new Set(account?.permissions ?? []);
  const can = (permission: string) => account?.role === "ADMIN" || grants.has(permission);
  const permissionByPage: Record<PageName, string> = {
    dashboard: "alerts.view", alerts: "alerts.view", users: "users.view",
    activities: "activities.view", simulation: "alerts.investigate", rules: "rules.manage", accounts: "accounts.manage", workspace: "workspace.view",
  };
  const nav = (account?.role === "ADMIN"
    ? ADMIN_NAV.map(item => item.page === "workspace"
        ? { ...item, label: account?.job_role ? `${account.job_role} Workspace` : item.label }
        : item)
        : account?.role === "ANALYST" && (!account.job_role || account.job_role.toLowerCase().includes("analyst"))
      ? [
          { page: "alerts" as PageName, label: "Alerts & investigations" },
          { page: "simulation" as PageName, label: "Detection lab" },
          { page: "workspace" as PageName, label: account?.job_role ? `${account.job_role} Workspace` : "My Workspace" },
        ]
      : [
          { page: "workspace" as PageName, label: account?.job_role ? `${account.job_role} Workspace` : "My Workspace" },
        ]
  ).filter(item => item.page === "workspace" || can(permissionByPage[item.page]));

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <img src="/eagle-eye-logo.svg" alt="Eagle Eye — See More, Stay Ahead" className="brand-logo" />
        </div>
        <nav aria-label="Main">
          {nav.map((item) => (
            <a key={item.page} href={`#/${item.page}`} aria-current={current === item.page ? "page" : undefined}>
              {item.page === "accounts" && pendingResetCount > 0 ? `${item.label} · ${pendingResetCount} reset request${pendingResetCount === 1 ? "" : "s"}` : item.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="account">
            <strong>{account?.username}</strong>
            <span>{account?.role === "ADMIN" ? "Administrator · Full access" : `${account?.job_role || account?.role || "User"} · Permission-based access`}</span>
          </div>
          <button className="button button-ghost" onClick={() => logout()}>
            Log out
          </button>
        </div>
      </aside>
      <div className="content">
        <div className="top-strip">
          <p className="synthetic-banner">
            Demonstration system. All employees and activity are synthetic; an alert is a lead for review, not proof
            of wrongdoing.
          </p>
          <button className="button button-theme" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
            <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span> {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
        <main id="main">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}
