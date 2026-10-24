import { useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { ActivitiesPage } from "./pages/ActivitiesPage";
import { AccountsPage } from "./pages/AccountsPage";
import { AlertDetailPage } from "./pages/AlertDetailPage";
import { AlertsPage } from "./pages/AlertsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { RulesPage } from "./pages/RulesPage";
import { SimulationPage } from "./pages/SimulationPage";
import { UserDetailPage } from "./pages/UserDetailPage";
import { UsersPage } from "./pages/UsersPage";
import { WorkspacePage } from "./pages/WorkspacePage";
import { useRoute } from "./utils/router";

export function App() {
  const { account, checking } = useAuth();
  const route = useRoute();
  const isAdmin = account?.role === "ADMIN";

  if (checking) return <div className="state">Checking your session…</div>;
  if (!account) return <LoginPage />;

  // Navigation is driven by explicit API permission grants, not by the role label.
  const grants = new Set(account?.permissions ?? []);
  const can = (permission: string) => isAdmin || grants.has(permission);
  const pagePermission: Record<string, string> = {
    dashboard: "alerts.view", alerts: "alerts.view", users: "users.view",
    activities: "activities.view", simulation: "alerts.investigate",
    rules: "rules.manage", accounts: "accounts.manage", workspace: "workspace.view",
  };
   const allowedPages: string[] =
    isAdmin
      ? Object.entries(pagePermission)
          .filter(([page, permission]) => page === "workspace" || can(permission))
          .map(([page]) => page)
            : account.role === "ANALYST" && (!account.job_role || account.job_role.toLowerCase().includes("analyst"))
        ? ["alerts", "simulation"].filter(page => can(pagePermission[page]))
        : ["workspace"];

  const activePage = allowedPages.includes(route.page)
    ? route.page
    : (allowedPages[0] as typeof route.page | undefined) ?? "workspace";

  if (!allowedPages.includes(route.page) && route.page !== activePage) {
    window.location.hash = `#/${activePage}`;
  }

  let page;
  switch (activePage) {
    case "alerts":
      page = route.id ? <AlertDetailPage key={route.id} alertId={route.id} /> : <AlertsPage />;
      break;
    case "users":
      page = route.id ? <UserDetailPage key={route.id} userId={route.id} /> : <UsersPage />;
      break;
    case "activities":
      page = <ActivitiesPage />;
      break;
    case "simulation":
      page = <SimulationPage />;
      break;
    case "rules":
      page = <RulesPage />;
      break;
    case "accounts":
      page = <AccountsPage />;
      break;
    case "workspace":
      page = <WorkspacePage />;
      break;
    default:
      page = <DashboardPage />;
  }
  return <Layout current={activePage}>{page}</Layout>;
}
