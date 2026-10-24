import type { Activity, AlertSummary, Page, RiskHistoryPoint, UserDetail } from "../api/types";
import { useApi } from "../api/useApi";
import { RiskBadge, SensitivityText, SimulatedTag, StatusBadge } from "../components/Badges";
import { ColumnChart } from "../components/charts/ColumnChart";
import { HorizontalBars } from "../components/charts/HorizontalBars";
import { DataState } from "../components/DataState";
import { PageHeader } from "../components/Layout";
import { formatDateTime, formatScore, humanize, RISK_COLORS } from "../utils/format";
import { navigate } from "../utils/router";

// Baseline features shown to the analyst (the most meaningful ones for a person to read).
const BASELINE_FEATURES = [
  "total_events", "login_count", "night_login_count", "file_access_count", "download_count",
  "download_mb", "delete_count", "usb_event_count", "sensitive_access_count", "unique_resources",
];

const BASELINE_EXPLANATION: Record<string, string> = {
  INDIVIDUAL: "Built from this user's own previous active days.",
  PEER_GROUP: "Not enough personal history yet, so the department's history is used.",
  DEFAULT: "No usable history yet, so documented default values are used.",
};

export function UserDetailPage({ userId }: { userId: number }) {
  const user = useApi<UserDetail>(`/users/${userId}`);
  const history = useApi<RiskHistoryPoint[]>(`/users/${userId}/risk-history?days=30`);
  const activities = useApi<Page<Activity>>(`/users/${userId}/activities?page_size=12`);
  const alerts = useApi<Page<AlertSummary>>(`/users/${userId}/alerts?page_size=10`);
  const u = user.data;

  return (
    <>
      <p className="breadcrumb"><a href="#/users">Users</a> / {u?.username ?? `User #${userId}`}</p>
      <DataState loading={user.loading && !u} error={user.error} onRetry={user.reload}>
        {u && (
          <>
            <PageHeader
              title={u.username}
              subtitle={`${u.job_role}, ${u.department}. Last activity ${formatDateTime(u.last_activity_at)}.`}
              actions={<>{u.is_synthetic && <SimulatedTag />}<RiskBadge level={u.current_risk_level} score={u.current_risk_score} /></>}
            />

            <section className="panel">
              <h2>Daily risk, last 30 days</h2>
              <p className="panel-note">One column per analyzed day. The line marks the alert threshold. Click a column with an alert to open it.</p>
              <DataState loading={history.loading} error={history.error} empty={history.data?.length === 0}
                         emptyMessage="No analyzed days yet.">
                {history.data && (
                  <ColumnChart
                    ariaLabel="Daily risk score"
                    maxValue={100}
                    width={1100}
                    guideLine={{ value: 50, label: "alert threshold" }}
                    columns={history.data.map((point) => ({
                      key: String(point.alert_id ?? ""),
                      label: point.window_date.slice(5),
                      parts: [{ value: point.risk_score, color: RISK_COLORS[point.risk_level], label: `risk ${formatScore(point.risk_score)}` }],
                    }))}
                    onColumnClick={(alertId) => { if (alertId) navigate(`/alerts/${alertId}`); }}
                  />
                )}
              </DataState>
            </section>

            <div className="grid-2">
              <section className="panel">
                <h2>Behavioral baseline</h2>
                {u.profile ? (
                  <>
                    <p className="panel-note">
                      {humanize(u.profile.baseline_type)} baseline, {u.profile.observation_days} observed days.{" "}
                      {BASELINE_EXPLANATION[u.profile.baseline_type]}
                    </p>
                    <table className="table table-compact">
                      <thead><tr><th>Feature (per day)</th><th>Average</th><th>Usual variation (±)</th></tr></thead>
                      <tbody>
                        {BASELINE_FEATURES.map((name) => (
                          <tr key={name}>
                            <td>{humanize(name)}</td>
                            <td>{formatScore(u.profile!.feature_means[name])}</td>
                            <td>{formatScore(u.profile!.feature_stds[name])}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                ) : (
                  <p className="muted">No baseline yet: it is built the first time this user's activity is analyzed.</p>
                )}
              </section>

              <section className="panel">
                <h2>Activity, last {u.statistics.period_days} days</h2>
                <p className="panel-note">
                  {u.statistics.active_days} active days, {u.statistics.average_events_per_active_day} events per active day.
                  Devices: {u.statistics.devices.join(", ") || "none"}.
                </p>
                <HorizontalBars ariaLabel="Events per type"
                                items={Object.entries(u.statistics.event_counts)
                                  .sort((a, b) => b[1] - a[1])
                                  .map(([type, count]) => ({ label: humanize(type), value: count }))} />
              </section>
            </div>

            <div className="grid-2">
              <section className="panel">
                <h2>Previous alerts</h2>
                <DataState loading={alerts.loading} error={alerts.error} empty={alerts.data?.total === 0}
                           emptyMessage="No alerts for this user.">
                  <ul className="simple-list">
                    {alerts.data?.items.map((alert) => (
                      <li key={alert.id}>
                        <a href={`#/alerts/${alert.id}`}>{alert.window_date}</a>
                        <RiskBadge level={alert.risk_level} score={alert.risk_score} />
                        <StatusBadge status={alert.status} />
                      </li>
                    ))}
                  </ul>
                </DataState>
              </section>

              <section className="panel">
                <div className="panel-title-row">
                  <h2>Recent activity</h2>
                  <a href={`#/activities?user_id=${userId}`}>Full log</a>
                </div>
                <DataState loading={activities.loading} error={activities.error} empty={activities.data?.total === 0}>
                  <table className="table table-compact">
                    <tbody>
                      {activities.data?.items.map((activity) => (
                        <tr key={activity.id}>
                          <td className="nowrap">{formatDateTime(activity.timestamp)}</td>
                          <td>{humanize(activity.event_type)}</td>
                          <td className="truncate">{activity.resource ?? ""}</td>
                          <td><SensitivityText value={activity.sensitivity} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </DataState>
              </section>
            </div>
          </>
        )}
      </DataState>
    </>
  );
}
